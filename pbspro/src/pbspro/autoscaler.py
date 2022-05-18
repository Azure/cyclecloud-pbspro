import os
import sys
from argparse import ArgumentParser
from typing import Any, Dict, List, Optional

import hpc.autoscale.job.driver
from hpc.autoscale import hpclogging as logging
from hpc.autoscale.job import demandcalculator as dcalclib
from hpc.autoscale.job import demandprinter
from hpc.autoscale.job.demand import DemandResult
from hpc.autoscale.job.demandcalculator import DemandCalculator
from hpc.autoscale.node.nodehistory import NodeHistory
from hpc.autoscale.node.nodemanager import NodeManager, new_node_manager
from hpc.autoscale.results import DefaultContextHandler, register_result_handler
from hpc.autoscale.util import SingletonLock, json_load

from pbspro import environment as envlib
from pbspro.driver import PBSProDriver
from pbspro.environment import PBSProEnvironment

_exit_code = 0


def autoscale_pbspro(
    config: Dict[str, Any],
    pbs_env: Optional[PBSProEnvironment] = None,
    pbs_driver: Optional[PBSProDriver] = None,
    ctx_handler: Optional[DefaultContextHandler] = None,
    node_history: Optional[NodeHistory] = None,
    dry_run: bool = False,
) -> DemandResult:
    global _exit_code

    assert not config.get("read_only", False)
    if dry_run:
        logging.warning("Running pbs autoscaler in dry run mode")
        # allow multiple instances
        config["lock_file"] = None
        # put in read only mode
        config["read_only"] = True

    # interface to PBSPro, generally by cli
    if pbs_driver is None:
        # allow tests to pass in a mock
        pbs_driver = PBSProDriver(config)

    if pbs_env is None:
        pbs_env = envlib.from_driver(config, pbs_driver)

    pbs_driver.initialize()

    config = pbs_driver.preprocess_config(config)

    logging.debug("Driver = %s", pbs_driver)

    demand_calculator = calculate_demand(config, pbs_env, ctx_handler, node_history)

    failed_nodes = demand_calculator.node_mgr.get_failed_nodes()
    for node in pbs_env.scheduler_nodes:
        if "down" in node.metadata.get("pbs_state", ""):
            failed_nodes.append(node)
    pbs_driver.handle_failed_nodes(failed_nodes)

    demand_result = demand_calculator.finish()

    if ctx_handler:
        ctx_handler.set_context("[joining]")

    # details here are that we pass in nodes that matter (matched) and the driver figures out
    # which ones are new and need to be added
    joined = pbs_driver.add_nodes_to_cluster(
        [x for x in demand_result.compute_nodes if x.exists]
    )

    pbs_driver.handle_post_join_cluster(joined)

    if ctx_handler:
        ctx_handler.set_context("[scaling]")

    # bootup all nodes. Optionally pass in a filtered list
    if demand_result.new_nodes:
        if not dry_run:
            demand_calculator.bootup()

    if not dry_run:
        demand_calculator.update_history()

    # we also tell the driver about nodes that are unmatched. It filters them out
    # and returns a list of ones we can delete.
    idle_timeout = int(config.get("idle_timeout", 300))
    boot_timeout = int(config.get("boot_timeout", 3600))
    logging.fine("Idle timeout is %s", idle_timeout)

    unmatched_for_5_mins = demand_calculator.find_unmatched_for(at_least=idle_timeout)
    timed_out_booting = demand_calculator.find_booting(at_least=boot_timeout)

    # I don't care about nodes that have keep_alive=true
    timed_out_booting = [n for n in timed_out_booting if not n.keep_alive]

    timed_out_to_deleted = []
    unmatched_nodes_to_delete = []

    if timed_out_booting:
        logging.info(
            "The following nodes have timed out while booting: %s", timed_out_booting
        )
        timed_out_to_deleted = pbs_driver.handle_boot_timeout(timed_out_booting) or []
        for node in timed_out_booting:
            node.closed = True

    if unmatched_for_5_mins:
        logging.info(
            "The following nodes have reached the idle_timeout (%s): %s",
            idle_timeout,
            unmatched_for_5_mins,
        )
        unmatched_nodes_to_delete = (
            pbs_driver.handle_draining(unmatched_for_5_mins) or []
        )

    nodes_to_delete = []
    for node in timed_out_to_deleted + unmatched_nodes_to_delete:
        if node.assignments:
            logging.warning(
                "%s has jobs assigned to it so we will take no action.", node
            )
            continue
        nodes_to_delete.append(node)

    if nodes_to_delete:
        try:
            logging.info("Deleting %s", [str(n) for n in nodes_to_delete])
            delete_result = demand_calculator.delete(nodes_to_delete)

            if delete_result:
                # in case it has anything to do after a node is deleted (usually just remove it from the cluster)
                pbs_driver.handle_post_delete(delete_result.nodes)
        except Exception as e:
            _exit_code = 1
            logging.warning("Deletion failed, will retry on next iteration: %s", e)
            logging.exception(str(e))

    print_demand(config, demand_result, log=not dry_run)

    return demand_result


def new_demand_calculator(
    config: Dict,
    pbs_env: Optional[PBSProEnvironment] = None,
    pbs_driver: Optional["PBSProDriver"] = None,
    ctx_handler: Optional[DefaultContextHandler] = None,
    node_history: Optional[NodeHistory] = None,
    singleton_lock: Optional[SingletonLock] = None,
    node_mgr: Optional[NodeManager] = None,
) -> DemandCalculator:
    if pbs_driver is None:
        pbs_driver = PBSProDriver(config)

    if pbs_env is None:
        pbs_env = envlib.from_driver(config, pbs_driver)

    if node_history is None:
        node_history = pbs_driver.new_node_history(config)

    # keep it as a config
    node_mgr = node_mgr or new_node_manager(
        config, existing_nodes=pbs_env.scheduler_nodes
    )
    pbs_driver.preprocess_node_mgr(config, node_mgr)
    singleton_lock = singleton_lock or pbs_driver.new_singleton_lock(config)
    assert singleton_lock

    demand_calculator = dcalclib.new_demand_calculator(
        config,
        node_mgr=node_mgr,
        node_history=node_history,
        node_queue=pbs_driver.new_node_queue(config),
        singleton_lock=singleton_lock,  # it will handle the none case,
        existing_nodes=pbs_env.scheduler_nodes,
    )

    ccnode_id_added = False

    for bucket in demand_calculator.node_mgr.get_buckets():

        # ccnodeid will almost certainly not be defined. It just needs
        # to be definede once, so we will add a default for all nodes
        # the first time we see it is missingg
        if "ccnodeid" not in bucket.resources and not ccnode_id_added:
            hpc.autoscale.job.driver.add_ccnodeid_default_resource(
                demand_calculator.node_mgr
            )
            ccnode_id_added = True

    return demand_calculator


def calculate_demand(
    config: Dict,
    pbs_env: PBSProEnvironment,
    ctx_handler: Optional[DefaultContextHandler] = None,
    node_history: Optional[NodeHistory] = None,
) -> DemandCalculator:

    demand_calculator = new_demand_calculator(
        config, pbs_env, ctx_handler, node_history
    )

    for job in pbs_env.jobs:
        if job.metadata.get("job_state") == "running":
            continue

        if ctx_handler:
            ctx_handler.set_context("[job {}]".format(job.name))
        demand_calculator.add_job(job)

    return demand_calculator


def print_demand(
    config: Dict,
    demand_result: DemandResult,
    output_columns: Optional[List[str]] = None,
    output_format: Optional[str] = None,
    log: bool = False,
) -> None:
    # and let's use the demand printer to print the demand_result.
    if not output_columns:
        output_columns = config.get(
            "output_columns",
            [
                "name",
                "hostname",
                "job_ids",
                "*hostgroups",
                "exists",
                "required",
                "managed",
                "slots",
                "*slots",
                "vm_size",
                "memory",
                "vcpu_count",
                "state",
                "placement_group",
                "create_time_remaining",
                "idle_time_remaining",
            ],
        )

    if "all" in output_columns:  # type: ignore
        output_columns = []

    output_format = output_format or "table"

    demandprinter.print_demand(
        output_columns, demand_result, output_format=output_format, log=log,
    )
    return demand_result


def new_driver(config: Dict) -> "PBSProDriver":
    import importlib

    pbs_config = config.get("pbs", {})

    driver_expr = pbs_config.get("driver", "pbs.driver.new_driver")

    if "." not in driver_expr:
        raise BadDriverError(driver_expr)

    module_expr, func_or_class_name = driver_expr.rsplit(".", 1)

    try:
        module = importlib.import_module(module_expr)
    except Exception as e:
        logging.exception(
            "Could not load module %s. Is it in the"
            + " PYTHONPATH environment variable? %s",
            str(e),
            sys.path,
        )
        raise

    func_or_class = getattr(module, func_or_class_name)
    return func_or_class(config)


class BadDriverError(RuntimeError):
    def __init__(self, bad_expr: str) -> None:
        super().__init__()
        self.bad_expr = bad_expr
        self.message = str(self)

    def __str__(self) -> str:
        return (
            "Expected pbs.driver=module.func_name"
            + " or pbs.driver=module.class_name. Got {}".format(self.bad_expr)
        )

    def __repr__(self) -> str:
        return str(self)


def main() -> int:
    ctx_handler = register_result_handler(DefaultContextHandler("[initialization]"))

    parser = ArgumentParser()
    parser.add_argument(
        "-c", "--config", help="Path to autoscale config.", required=True
    )
    args = parser.parse_args()
    config_path = os.path.expanduser(args.config)

    if not os.path.exists(config_path):
        print("{} does not exist.".format(config_path), file=sys.stderr)
        return 1

    config = json_load(config_path)

    autoscale_pbspro(config, ctx_handler=ctx_handler)

    return _exit_code


if __name__ == "__main__":
    sys.exit(main())
