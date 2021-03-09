import sys
from argparse import ArgumentParser
from typing import Dict, Iterable, List, Optional, Tuple

from hpc.autoscale import clilib
from hpc.autoscale.job.demandcalculator import DemandCalculator
from hpc.autoscale.job.driver import SchedulerDriver
from hpc.autoscale.job.job import Job
from hpc.autoscale.results import DefaultContextHandler
from hpc.autoscale.util import partition_single

from pbspro import environment
from pbspro.autoscaler import new_demand_calculator
from pbspro.driver import PBSProDriver
from pbspro.parser import PBSProParser, get_pbspro_parser, set_pbspro_parser
from pbspro.pbscmd import PBSCMD
from pbspro.resource import read_resource_definitions


class PBSCLI(clilib.CommonCLI):
    def __init__(self) -> None:
        clilib.CommonCLI.__init__(self, "pbspro")
        # bootstrap parser
        set_pbspro_parser(PBSProParser({}))
        self.pbscmd = PBSCMD(get_pbspro_parser())
        # lazily initialized
        self.__pbs_env: Optional[environment.PBSProEnvironment] = None
        self.__driver: Optional[PBSProDriver] = None

    def connect(self, config: Dict) -> None:
        """Tests connection to CycleCloud"""
        self._node_mgr(config)

    def _initialize(self, command: str, config: Dict) -> None:

        resource_definitions = read_resource_definitions(self.pbscmd, config)
        set_pbspro_parser(PBSProParser(resource_definitions))
        self.pbscmd = PBSCMD(get_pbspro_parser())

    def _driver(self, config: Dict) -> SchedulerDriver:
        if self.__driver is None:
            self.__driver = PBSProDriver(self.pbscmd)
        return self.__driver

    def _initconfig(self, config: Dict) -> None:
        pass

    def _initconfig_parser(self, parser: ArgumentParser) -> None:
        pass

    def _default_output_columns(
        self, config: Dict, cmd: Optional[str] = None
    ) -> List[str]:
        driver = self._driver(config)
        env = self._pbs_env(driver)
        resource_columns = []
        for res_name, res_def in env.resource_definitions.items():
            if res_name in ["aoe", "instance_id", "vnode", "host", "arch", "vm_size"]:
                continue
            if res_def.is_host:
                if res_def.name == "ccnodeid":
                    continue
                elif res_def.is_consumable and res_def.type.name not in [
                    "string",
                    "stringarray",
                ]:
                    resource_columns.append("/{}".format(res_name))
                else:
                    if res_name == "group_id":
                        resource_columns.append("group_id[-8:]")
                    else:
                        resource_columns.append(res_name)

        resource_columns = sorted(resource_columns)

        return config.get(
            "output_columns",
            [
                "name",
                "hostname",
                "pbs_state",
                "job_ids",
                "state",
                "vm_size",
            ]
            + resource_columns
            + [
                "instance_id[:11]",
                "ctr@create_time_remaining",
                "itr@idle_time_remaining",
            ],
        )

    def _pbs_env(self, pbs_driver: PBSProDriver) -> environment.PBSProEnvironment:
        if self.__pbs_env is None:
            self.__pbs_env = environment.from_driver(pbs_driver)
        return self.__pbs_env

    def _demand_calc(
        self, config: Dict, driver: SchedulerDriver
    ) -> Tuple[DemandCalculator, List[Job]]:
        pbs_driver: PBSProDriver = driver
        pbs_env = self._pbs_env(pbs_driver)
        dcalc = new_demand_calculator(config, pbs_env=pbs_env, pbs_driver=pbs_driver)
        return dcalc, pbs_env.jobs

    def _setup_shell_locals(self, config: Dict) -> Dict:
        """
        Provides read only interactive shell. type pbsprohelp()
        in the shell for more information
        """
        ctx = DefaultContextHandler("[interactive-readonly]")

        pbs_driver = PBSProDriver()
        pbs_env = self._pbs_env(pbs_driver)

        def pbsprohelp() -> None:
            print("config               - dict representing autoscale configuration.")
            print("cli                  - object representing the CLI commands")
            print(
                "pbs_env              - object that contains data structures for queues, resources etc"
            )
            print("queues               - dict of queue name -> PBSProQueue object")

            print("jobs                 - dict of job id -> Autoscale Job")
            print(
                "scheduler_nodes      - dict of hostname -> node objects. These represent purely what"
                "                  the scheduler sees without additional booting nodes / information from CycleCloud"
            )
            print(
                "resource_definitions - dict of resource name -> PBSProResourceDefinition objects."
            )
            print(
                "default_scheduler    - PBSProScheduler object representing the default scheduler."
            )
            print(
                "pbs_driver           - PBSProDriver object that interacts directly with PBS and implements"
                "                    PBS specific behavior for scalelib."
            )
            print(
                "demand_calc          - ScaleLib DemandCalculator - pseudo-scheduler that determines the what nodes are unnecessary"
            )
            print(
                "node_mgr             - ScaleLib NodeManager - interacts with CycleCloud for all node related"
                + "                    activities - creation, deletion, limits, buckets etc."
            )
            print("pbsprohelp            - This help function")

        # try to make the key "15" instead of "15.hostname" if only
        # a single submitter was in use
        num_scheds = len(set([x.name.split(".", 1)[-1] for x in pbs_env.jobs]))
        if num_scheds == 1:
            jobs_dict = partition_single(pbs_env.jobs, lambda j: j.name.split(".")[0])
        else:
            jobs_dict = partition_single(pbs_env.jobs, lambda j: j.name)

        sched_nodes_dict = partition_single(
            pbs_env.scheduler_nodes, lambda n: n.hostname
        )

        pbs_env.queues = clilib.ShellDict(pbs_env.queues)

        for snode in pbs_env.scheduler_nodes:
            snode.shellify()

        pbs_env.resource_definitions = clilib.ShellDict(pbs_env.resource_definitions)

        demand_calc, _ = self._demand_calc(config, pbs_driver)

        shell_locals = {
            "config": config,
            "cli": self,
            "ctx": ctx,
            "pbs_env": pbs_env,
            "queues": pbs_env.queues,
            "jobs": clilib.ShellDict(jobs_dict, "j"),
            "scheduler_nodes": clilib.ShellDict(sched_nodes_dict),
            "resource_definitions": pbs_env.resource_definitions,
            "default_scheduler": pbs_env.default_scheduler,
            "pbs_driver": pbs_driver,
            "demand_calc": demand_calc,
            "node_mgr": demand_calc.node_mgr,
            "pbsprohelp": pbsprohelp,
        }

        return shell_locals

    def validate(self, config: Dict) -> None:
        """
        Best-effort validation of your PBS environment's compatibility with this autoscaler.
        """
        pbs_driver = PBSProDriver()
        pbs_env = self._pbs_env(pbs_driver)
        sched = pbs_env.default_scheduler
        if not sched:
            print("Could not find a default server.", file=sys.stderr)
            sys.exit(1)

        exit = 0

        for attr in ["ungrouped", "group_id"]:
            if attr not in sched.resources_for_scheduling:
                print(
                    "{} is not defined for line 'resources:' in {}/sched_priv.".format(
                        attr, sched.sched_priv
                    )
                    + " Please add this and restart PBS"
                )
                exit = 1

        if sched.node_group_key and not sched.node_group_enable:
            print(
                "node_group_key is set to '{}' but node_group_enable is false".format(
                    sched.node_group_key
                ),
                file=sys.stderr,
            )
            exit = 1
        elif not sched.node_group_enable:
            print(
                "node_group_enable is false, so MPI/parallel jobs may not work if multiple placement groups are created.",
                file=sys.stderr,
            )
            exit = 1

        if not sched.only_explicit_psets:
            print(
                "only_explicit_psets should be set to true in your sched_config if you are using MPI or colocated jobs.",
                file=sys.stderr,
            )
            exit = 1
        if not sched.do_not_span_psets:
            print(
                "do_not_span_psets should be set to true in your sched_config if you are using MPI or colocated jobs.",
                file=sys.stderr,
            )
            exit = 1

        sys.exit(exit)


def main(argv: Iterable[str] = None) -> None:
    clilib.main(argv or sys.argv[1:], "pbspro", PBSCLI())


if __name__ == "__main__":
    main()
