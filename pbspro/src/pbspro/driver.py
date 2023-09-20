import datetime
import os
import re
import socket
from functools import lru_cache
from subprocess import CalledProcessError, SubprocessError
from typing import Any, Dict, List, Optional, Set, Tuple

from hpc.autoscale import hpclogging as logging
from hpc.autoscale import hpctypes as ht
from hpc.autoscale.job.driver import SchedulerDriver
from hpc.autoscale.job.job import Job, PackingStrategy
from hpc.autoscale.job.nodequeue import NodeQueue
from hpc.autoscale.job.schedulernode import SchedulerNode
from hpc.autoscale.node.constraints import SharedResource
from hpc.autoscale.node.node import Node
from hpc.autoscale.node.nodehistory import NodeHistory
from hpc.autoscale.node.nodemanager import NodeManager
from hpc.autoscale.results import EarlyBailoutResult
from hpc.autoscale.util import (
    is_valid_hostname,
    parse_boot_timeout,
    parse_idle_timeout,
    partition,
    partition_single,
)

from pbspro.constants import PBSProJobStates
from pbspro.parser import get_pbspro_parser
from pbspro.pbscmd import PBSCMD
from pbspro.pbsqueue import PBSProQueue, read_queues
from pbspro.resource import PBSProResourceDefinition
from pbspro.scheduler import PBSProScheduler, read_schedulers

# sched_config = "/var/spool/pbs/sched_priv/sched_config"


class PBSEnvironmentError(RuntimeError):
    ...


class PBSProDriver(SchedulerDriver):
    """
    The main interface for interacting with the PBS system and also
    overrides the generic SchedulerDriver with PBS specific behavior.
    """

    def __init__(
        self,
        config: Dict,
        pbscmd: Optional[PBSCMD] = None,
        resource_definitions: Optional[Dict[str, PBSProResourceDefinition]] = None,
        down_timeout: int = 300,
    ) -> None:
        super().__init__("pbspro")
        self.config = config
        self.pbscmd = pbscmd or PBSCMD(get_pbspro_parser())
        self.__queues: Optional[Dict[str, PBSProQueue]] = None
        self.__shared_resources: Optional[Dict[str, SharedResource]]
        self.__resource_definitions = resource_definitions
        self.__read_only_resources: Optional[Set[str]] = None
        self.__jobs_cache: Optional[List[Job]] = None
        self.__scheduler_nodes_cache: Optional[List[Node]] = None
        self.__node_history: Optional[NodeHistory] = None
        self.down_timeout = down_timeout
        self.down_timeout_td = datetime.timedelta(seconds=self.down_timeout)

    @property
    def autoscale_home(self) -> str:
        if os.getenv("AUTOSCALE_HOME"):
            return os.environ["AUTOSCALE_HOME"]
        return os.path.join("/opt", "cycle", self.name)


    @property
    def resource_definitions(self) -> Dict[str, PBSProResourceDefinition]:
        if not self.__resource_definitions:
            self.__resource_definitions = get_pbspro_parser().resource_definitions
        return self.__resource_definitions

    @property
    def read_only_resources(self) -> Set[str]:
        if not self.__read_only_resources:
            self.__read_only_resources = set(
                [r.name for r in self.resource_definitions.values() if r.read_only]
            )
        return self.__read_only_resources

    def initialize(self) -> None:
        """
        Placeholder for subclasses to customize initialization
        By default, we make sure that the ccnodeid exists
        """
        try:
            self.pbscmd.qmgr("list", "resource", "ccnodeid")
        except CalledProcessError:
            self.pbscmd.qmgr("create", "resource", "ccnodeid", "type=string,", "flag=h")

    def preprocess_config(self, config: Dict) -> Dict:
        """
        Placeholder for subclasses to customize config dynamically
        """
        return config

    def preprocess_node_mgr(self, config: Dict, node_mgr: NodeManager) -> None:
        """
        We add a default resource to map group_id to node.placement_group
        """
        super().preprocess_node_mgr(config, node_mgr)

        def group_id(node: Node) -> str:
            return node.placement_group if node.placement_group else "_none_"

        node_mgr.add_default_resource({}, "group_id", group_id, allow_none=False)

        def ungrouped(node: Node) -> str:
            return str(not bool(node.placement_group)).lower()

        node_mgr.add_default_resource({}, "ungrouped", ungrouped)
        pbsnodes_response = self.pbscmd.pbsnodes_parsed("-a")
        by_hostname = partition(
            pbsnodes_response, lambda x: x.get("name")
        )

        for node in node_mgr.get_nodes():
            # close out any failed nodes up front
            if node.state == "Failed":
                node.closed = True
            
            if not node.hostname:
                continue
            
            # assign keep_offline to these nodes and close them off from further
            # assignment
            pbsnodes_record = by_hostname.get(node.hostname)

            if pbsnodes_record and pbsnodes_record[0].get("resources_available.ccnodeid"):
                comment = pbsnodes_record[0].get("comment", "")
                if comment.startswith("cyclecloud keep offline"):
                    node.assign("keep_offline")
                    node.closed = True
                    continue

    def validate_nodes(
        self, scheduler_nodes: List[SchedulerNode], cc_nodes: List[Node]
    ) -> None:
        cc_by_node_id = partition_single(
            cc_nodes, lambda n: n.delayed_node_id.node_id or n.hostname_or_uuid,
        )
        # Special case handling when users change their hostname after the node is already
        # added to the cluster. Note that the hostname MUST MATCH THAT IN CYCLECLOUD!
        # We also only do this for state-unknown,down nodes.

        to_remove = []
        for snode in scheduler_nodes:
            ccnodeid = snode.resources.get("ccnodeid")
            pbs_hostname = snode.hostname.lower()
            if not ccnodeid:
                continue

            should_remove = False
            if ccnodeid not in cc_by_node_id:
                logging.warning(
                    f"{snode.name} {snode.hostname} exists in the cluster but not in CycleCloud. Removing it."
                )
                should_remove = True

            elif cc_by_node_id[ccnodeid].state == "Failed":
                logging.warning(
                    f"{snode.name} {snode.hostname} exists in the cluster but is in a Failed state. Removing it."
                )
                should_remove = True

            if should_remove:
                try:
                    to_remove.append(snode)
                    self.handle_post_delete([snode])
                except Exception:
                    logging.exception(f"Failed to remove node {pbs_hostname}")
                continue

            cc_node = cc_by_node_id[ccnodeid]
            cc_hostname = cc_node.hostname.lower()

            if pbs_hostname != cc_hostname:
                logging.warning(
                    f"The scheduler reports that node {cc_node.name} with node id "
                    + f"{ccnodeid} has hostname {pbs_hostname}, but CycleCloud reports "
                    + f"the hostname as {cc_hostname}"
                )

                if "busy" in snode.metadata.get("pbs_state", ""):
                    continue

                if "down" in snode.metadata.get("pbs_state", ""):
                    logging.warning(
                        f"Removing node {pbs_hostname} so that the correct hostname ({cc_hostname}) can join."
                    )
                    try:
                        to_remove.append(snode)
                        self.handle_post_delete([snode])
                    except Exception:
                        logging.exception(f"Failed to remove node {pbs_hostname}")
        for snode in to_remove:
            scheduler_nodes.remove(snode)

    def handle_failed_nodes(self, nodes: List[Node]) -> List[Node]:
        to_delete = []
        to_drain = []
        now = datetime.datetime.now()

        for node in nodes:

            if node.keep_alive:
                continue

            if node.state == "Failed":
                # node.closed = True
                # if self._is_boot_timeout(now, node):
                #     to_delete.append(node)
                continue

            if not node.resources.get("ccnodeid"):
                logging.fine(
                    "Attempting to delete %s but ccnodeid is not set yet.", node
                )
                continue

            job_state = node.metadata.get("pbs_state", "")
            if "down" in job_state:

                node.closed = True
                if "state-unknown" in job_state:
                    logging.warning(
                        "Node is in state-unknown - skipping scale down - %s", node
                    )
                    continue
                # no private_ip == no dns entry, so we can safely remove it
                if "offline" in job_state or not node.private_ip:
                    to_delete.append(node)
                else:
                    if self._down_long_enough(now, node):
                        to_drain.append(node)

        if to_drain:
            logging.info("Draining down nodes: %s", to_drain)
            self.handle_draining(to_drain)

        if to_delete:
            logging.info("Deleting down,offline nodes: %s", to_delete)
            return self.handle_post_delete(to_delete)
        return []

    def _down_long_enough(self, now: datetime.datetime, node: Node) -> bool:
        last_state_change_time_str = node.metadata.get("last_state_change_time")

        if last_state_change_time_str:
            last_state_change_time = datetime.datetime.strptime(
                last_state_change_time_str, "%a %b %d %H:%M:%S %Y"
            )
            delta = now - last_state_change_time
            if delta > self.down_timeout_td:
                return True
            else:
                seconds_remaining = (delta - self.down_timeout_td).seconds
                logging.debug(
                    "Down node %s still has %s seconds before setting to offline",
                    node,
                    seconds_remaining,
                )

        return False

    def _is_boot_timeout(self, now: datetime.datetime, node: Node) -> bool:
        boot_timeout = parse_boot_timeout(self.config, node)
        omega = node.create_time + datetime.timedelta(seconds=boot_timeout)
        return now > omega

    def _is_idle_timeout(self, now: datetime.datetime, node: Node) -> bool:
        idle_timeout = parse_idle_timeout(self.config, node)
        omega = node.create_time + datetime.timedelta(seconds=idle_timeout)
        return now > omega

    def add_nodes_to_cluster(self, nodes: List[Node]) -> List[Node]:
        self.initialize()
        node_history = self.new_node_history(self.config)
        ignored_nodes = node_history.find_ignored()
        ignored_node_ids = [n[0] for n in ignored_nodes if n[0]]

        all_nodes = self.pbscmd.pbsnodes_parsed("-a")
        by_ccnodeid = partition(
            all_nodes, lambda x: x.get("resources_available.ccnodeid")
        )

        ret = []
        for node in nodes:
            if node.metadata.get("_marked_offline_this_iteration_"):
                continue

            if node.delayed_node_id.node_id in ignored_node_ids:
                node.metadata["pbs_state"] = "removed!"
                continue

            if not node.hostname:
                continue

            if not node.private_ip:
                continue

            if node.state == "Failed":
                continue

            # special handling of "keep_offline" created during preprocess_node_mgr
            if "keep_offline" in node.assignments:
                continue

            node_id = node.delayed_node_id.node_id

            if not node_id:
                logging.error("%s does not have a nodeid! Skipping", node)
                continue

            if node_id in by_ccnodeid:
                skip_node = False
                for ndict in by_ccnodeid[node_id]:
                    if ndict["name"].lower() != node.hostname.lower():
                        logging.error(
                            "Duplicate hostname found for the same node id! %s and %s. See 'valid_hostnames' in autoscale as a possible workaround.",
                            node,
                            ndict["name"],
                        )
                        skip_node = True
                        break
                if skip_node:
                    continue

            if not is_valid_hostname(self.config, node):
                continue

            if not self._validate_reverse_dns(node):
                logging.fine(
                    "%s still has a hostname that can not be looked via reverse dns. This should repair itself.",
                    node,
                )
                continue

            if not node.resources.get("ccnodeid"):
                logging.info(
                    "%s is not managed by CycleCloud, or at least 'ccnodeid' is not defined. Ignoring",
                    node,
                )
                continue
            try:
                try:
                    ndicts = self.pbscmd.qmgr_parsed("list", "node", node.hostname)
                    if ndicts and ndicts[0].get("resources_available.ccnodeid"):
                        comment = ndicts[0].get("comment", "")

                        if "offline" in ndicts[0].get("state", "") and (
                            comment.startswith("cyclecloud offline")
                            or comment.startswith("cyclecloud joined")
                            or comment.startswith("cyclecloud restored")
                        ):
                            logging.info(
                                "%s is offline. Setting it back to online", node
                            )
                            self.pbscmd.pbsnodes(
                                "-r", node.hostname, "-C", "cyclecloud restored"
                            )
                        else:
                            logging.fine(
                                "ccnodeid is already defined on %s. Skipping", node
                            )
                        continue
                    # TODO RDH should we just delete it instead?
                    logging.info(
                        "%s already exists in this cluster. Setting resources.", node
                    )
                except CalledProcessError:
                    logging.info(
                        "%s does not exist in this cluster yet. Creating.", node
                    )
                    self.pbscmd.qmgr("create", "node", node.hostname)

                for res_name, res_value in node.resources.items():
                    # we set ccnodeid last, so that we can see that we have completely joined a node
                    # if and only if ccnodeid has been set
                    if res_name == "ccnodeid":
                        continue

                    if res_value is None:
                        continue

                    # TODO RDH track down
                    if res_name == "group_id" and res_value == "None":
                        continue

                    # skip things like host which are useful to set default resources on non-existent
                    # nodes for autoscale packing, but not on actual nodes
                    if res_name in self.read_only_resources:
                        continue

                    if res_name not in self.resource_definitions:
                        # TODO bump to a warning?
                        logging.fine(
                            "%s is an unknown PBS resource for node %s. Skipping this resource",
                            res_name,
                            node,
                        )
                        continue
                    res_value_str: str

                    # pbs size does not support decimals
                    if isinstance(res_value, ht.Size):
                        res_value_str = "{}{}".format(
                            int(res_value.value), res_value.magnitude
                        )
                    elif isinstance(res_value, bool):
                        res_value_str = "1" if bool else "0"
                    else:
                        res_value_str = str(res_value)

                    self.pbscmd.qmgr(
                        "set",
                        "node",
                        node.hostname,
                        "resources_available.{}={}".format(res_name, res_value_str),
                    )

                self.pbscmd.qmgr(
                    "set",
                    "node",
                    node.hostname,
                    "resources_available.{}={}".format(
                        "ccnodeid", node.resources["ccnodeid"]
                    ),
                )
                self.pbscmd.pbsnodes("-r", node.hostname, "-C", "cyclecloud joined")
                ret.append(node)
            except SubprocessError as e:
                logging.error(
                    "Could not fully add %s to cluster: %s. Will attempt next cycle",
                    node,
                    e,
                )

        return ret

    def handle_post_join_cluster(self, nodes: List[Node]) -> List[Node]:
        return nodes

    def handle_boot_timeout(self, nodes: List[Node]) -> List[Node]:
        return self._handle_draining(nodes, ignore_assignments=True)

    def handle_draining(self, nodes: List[Node]) -> List[Node]:
        return self._handle_draining(nodes, ignore_assignments=False)

    def _handle_draining(
        self, nodes: List[Node], ignore_assignments: bool = False
    ) -> List[Node]:
        """
        ignore_assignments - whether we should ignore assigned jobs by the autoscaler - note
                             we do not ignore actual running jobs, only presumed to run jobs.
        """
        # TODO batch these up, but keep it underneath the
        # max arg limit
        ret = []
        for node in nodes:
            if not node.hostname:
                logging.info("Node %s has no hostname. It is safe to delete.", node)
                ret.append(node)
                continue

            if not node.managed and not node.resources.get("ccnodeid"):
                logging.debug("Ignoring attempt to drain unmanaged %s", node)
                continue

            if "offline" in node.metadata.get("pbs_state", ""):
                if node.assignments and not ignore_assignments:
                    logging.info("Node %s has jobs still running on it.", node)
                    # node is already 'offline' i.e. draining, but a job is still running
                    continue
                else:
                    if node.metadata.get("_running_job_"):
                        logging.error(
                            "Attempt to shutdown and remove %s while running job(s) %s",
                            node,
                            node.assignments,
                        )
                    else:
                        # ok - it is offline _and_ no jobs are running on it.
                        ret.append(node)
            else:
                try:
                    self.pbscmd.pbsnodes(node.hostname)
                except CalledProcessError as e:

                    if "Error: Unknown node" in str(e.stderr):
                        ret.append(node)
                        continue
                    else:
                        logging.warning(
                            f"Unexpected failure while running 'pbsnodes {node.hostname}' - {e.stderr}"
                        )
                try:
                    self.pbscmd.pbsnodes(
                        "-o", node.hostname, "-C", "cyclecloud offline"
                    )
                    node.metadata["_marked_offline_this_iteration_"] = True

                    # # Due to a delay in when pbsnodes -o exits to when pbsnodes -a
                    # # actually reports an offline state, we will just optimistically set it to offline
                    # # otherwise ~50% of the time you get the old state (free)
                    # response = self.pbscmd.pbsnodes_parsed("-a", node.hostname)
                    # if response:
                    #     node.metadata["pbs_state"] = response[0]["state"]
                    node.metadata["pbs_state"] = "offline"

                except CalledProcessError as e:
                    if node.private_ip:
                        logging.error(
                            "'pbsnodes -o %s' failed and this node will not be scaled down: %s",
                            node.hostname,
                            e,
                        )
        return ret

    def handle_post_delete(self, nodes: List[Node]) -> List[Node]:
        ret = []
        for node in nodes:
            if not node.hostname:
                continue

            try:
                self.pbscmd.qmgr("list", "node", node.hostname)
            except CalledProcessError as e:
                if "Server has no node list" in str(e) or node.state == "Failed":
                    ret.append(node)
                    continue
                logging.error(
                    "Could not list node with hostname %s - %s", node.hostname, e
                )
                continue

            try:
                self.pbscmd.qmgr("delete", "node", node.hostname)
                node.metadata["pbs_state"] = "deleted"
                ret.append(node)
            except CalledProcessError as e:
                logging.error(
                    "Could not remove %s from cluster: %s. Will retry next cycle.",
                    node,
                    e,
                )
        return ret

    def new_node_queue(self, config: Dict) -> NodeQueue:
        return NodeQueue()

    @lru_cache(1)
    def read_schedulers(self) -> Dict[str, PBSProScheduler]:
        return read_schedulers(self.pbscmd, self.resource_definitions)

    @lru_cache(1)
    def read_default_scheduler(self) -> PBSProScheduler:
        schedulers = self.read_schedulers()

        for sched in schedulers.values():
            if sched.is_default:
                return sched

        raise RuntimeError("No default scheduler found!")

    def read_queues(
        self, shared_resources: Dict[str, SharedResource]
    ) -> Dict[str, PBSProQueue]:
        if self.__queues is None:
            self.__shared_resources = shared_resources
            self.__queues = read_queues(
                self.config, self.pbscmd, self.resource_definitions, shared_resources
            )
        assert shared_resources == self.__shared_resources
        return self.__queues

    def parse_jobs(
        self,
        queues: Dict[str, PBSProQueue],
        resources_for_scheduling: Set[str],
        force: bool = False,
    ) -> List[Job]:

        if force or self.__jobs_cache is None:
            self.__jobs_cache = parse_jobs(
                self.pbscmd, self.resource_definitions, queues, resources_for_scheduling
            )

        return self.__jobs_cache

    def _read_jobs_and_nodes(
        self, config: Dict
    ) -> Tuple[List[Job], List[SchedulerNode]]:
        """
        this is cached at the library level
        """
        scheduler = self.read_default_scheduler()
        queues = self.read_queues(scheduler.resource_state.shared_resources)
        nodes = self.parse_scheduler_nodes()
        jobs = self.parse_jobs(queues, scheduler.resources_for_scheduling)
        return jobs, nodes

    def parse_scheduler_nodes(self, force: bool = False,) -> List[Node]:
        if force or self.__scheduler_nodes_cache is None:
            self.__scheduler_nodes_cache = parse_scheduler_nodes(
                self.config, self.pbscmd, self.resource_definitions
            )
        return self.__scheduler_nodes_cache

    def _validate_reverse_dns(self, node: Node) -> bool:
        # let's make sure the hostname is valid and reverse
        # dns compatible before adding to GE

        # if there is no private ip, then the hostname was removed, most likely
        # by azure DNS
        if not node.private_ip:
            return True

        try:
            addr_info = socket.gethostbyaddr(node.private_ip)
        except Exception as e:
            logging.error(
                "Could not convert private_ip(%s) to hostname using gethostbyaddr() for %s: %s",
                node.private_ip,
                node,
                str(e),
            )
            return False

        addr_info_ips = addr_info[-1]
        if isinstance(addr_info_ips, str):
            addr_info_ips = [addr_info_ips]

        if node.private_ip not in addr_info_ips:
            logging.warning(
                "%s has a hostname that does not match the"
                + " private_ip (%s) reported by cyclecloud (%s)! Skipping",
                node,
                addr_info_ips,
                node.private_ip,
            )
            return False

        expect_multiple_entries = (
            node.software_configuration.get("cyclecloud", {})
            .get("hosts", {})
            .get("standalone_dns", {})
            .get("enabled", True)
        )

        addr_info_hostname = addr_info[0].split(".")[0]
        if addr_info_hostname.lower() != node.hostname.lower():
            if expect_multiple_entries:
                logging.warning(
                    "%s has a hostname that can not be queried via reverse"
                    + " dns (private_ip=%s cyclecloud hostname=%s reverse dns hostname=%s)."
                    + " This is common and usually repairs itself. Skipping",
                    node,
                    node.private_ip,
                    node.hostname,
                    addr_info_hostname,
                )
            else:
                logging.error(
                    "%s has a hostname that can not be queried via reverse"
                    + " dns (private_ip=%s cyclecloud hostname=%s reverse dns hostname=%s)."
                    + " If you have an entry for this address in your /etc/hosts file, please remove it.",
                    node,
                    node.private_ip,
                    node.hostname,
                    addr_info_hostname,
                )
            return False
        return True

    def __repr__(self) -> str:
        return "PBSProDriver(res_def={})".format(self.resource_definitions)


class PBSProNodeQueue(NodeQueue):
    def early_bailout(self, node: Node) -> EarlyBailoutResult:
        # TODO RDH if ncpus == 0
        # because right now, we never bail out.
        # not great if jobs use n-1 ncpus...
        return super().early_bailout(node)


def parse_jobs(
    pbscmd: PBSCMD,
    resource_definitions: Dict[str, PBSProResourceDefinition],
    queues: Dict[str, PBSProQueue],
    resources_for_scheduling: Set[str],
) -> List[Job]:
    """
    Parses PBS qstat output and creates relevant hpc.autoscale.job.job.Job objects
    """
    parser = get_pbspro_parser()
    # alternate format triggered by
    # -a, -i, -G, -H, -M, -n, -r, -s, -T, or -u
    ret: List[Job] = []

    response: Dict = pbscmd.qstat_json("-f", "-t")

    for job_id, jdict in response.get("Jobs", {}).items():
        job_id = job_id.split(".")[0]

        job_state = jdict.get("job_state")
        if not job_state:
            logging.warning("No job_state defined for job %s. Skipping", job_id)
            continue

        if job_state != PBSProJobStates.Queued:
            continue

        # ensure we don't autoscale jobs from disabled or non-started queues
        qname = jdict.get("queue")
        if not qname or qname not in queues:
            logging.warning("queue was not defined for job %s: ignoring", job_id)
            continue

        queue: PBSProQueue = queues[qname]
        if not queue.enabled:
            logging.fine("Skipping job %s from disabled queue %s", job_id, qname)
            continue

        if not queue.started:
            logging.fine("Skipping job %s from non-started queue %s", job_id, qname)
            continue

        # handle array vs individual jobs
        if jdict.get("array"):
            continue
        else:
            iterations = 1
            remaining = 1

        res_list = jdict["Resource_List"]
        res_list["schedselect"] = jdict["schedselect"]
        rdict = parser.convert_resource_list(res_list)

        pack = (
            PackingStrategy.PACK
            if rdict["place"]["arrangement"] in ["free", "pack"]
            else PackingStrategy.SCATTER
        )

        # SMP style jobs
        is_smp = (
            rdict["place"].get("grouping") == "host"
        )

        # pack jobs do not need to define node_count

        node_count = int(rdict.get("nodect", "0"))

        smp_multiplier = 1

        if is_smp:
            smp_multiplier = max(1, iterations) * max(1, node_count)
            # for key, value in list(rdict.items()):
            #     if isinstance(value, (float, int)):
            #         value = value * smp_multiplier
            iterations = node_count = 1

        effective_node_count = max(node_count, 1)

        # htc jobs set ungrouped=true. see our default htcq
        colocated = (
            not is_smp
            and queue.uses_placement
            and rdict.get("ungrouped", "false").lower() == "false"
        )

        sharing = rdict["place"].get("sharing")

        for n, chunk_base in enumerate(rdict["schedselect"]):

            chunk: Dict[str, Any] = {}

            chunk.update(rdict)

            if "ncpus" not in chunk_base:
                chunk["ncpus"] = chunk["ncpus"] // effective_node_count

            if smp_multiplier > 1:
                for key, value in list(chunk_base.items()):
                    if isinstance(value, (int, float)):
                        chunk_base[key] = value * smp_multiplier
            # do this _after_ rdict, since the chunks
            # will override the top level resources
            # e.g. notice that ncpus=4. This will be the rdict value
            # but the chunks have ncpus=2
            # Resource_List.ncpus = 4
            # Resource_List.nodect = 2
            # Resource_List.select = 2:ncpus=2

            chunk.update(chunk_base)
            working_constraint: Dict[str, Any] = {}
            constraints = [working_constraint]

            if colocated:
                working_constraint["in-a-placement-group"] = True

            my_job_id = job_id
            if len(rdict["schedselect"]) > 1:
                if "." in job_id:
                    job_index, host = job_id.split(".", 1)
                    my_job_id = "{}+{}.{}".format(job_index, n, host)
                else:
                    my_job_id = "{}+{}".format(job_id, n)

            if sharing == "excl":
                working_constraint["exclusive-task"] = True
            elif sharing == "exclhost":
                working_constraint["exclusive"] = True

            job_resources = {}

            for rname, rvalue in chunk.items():
                if rname in ["select", "schedselect", "place", "nodect"]:
                    continue

                if rname not in resources_for_scheduling:
                    if rname == "skipcyclesubhook":
                        continue
                    logging.warning(
                        "Ignoring resource %s as it was not defined in sched_config",
                        rname,
                    )
                    continue

                # add all resource requests here. By that, I mean
                # non resource requests, like exclusive, should be ignored
                # required for get_non_host_constraints
                job_resources[rname] = rvalue

                resource_def = resource_definitions.get(rname)

                # constraints are for the node/host
                # queue/scheduler level ones will be added using
                # > queue.get_non_host_constraints(job_resource)
                if not resource_def or not resource_def.is_host:
                    continue

                if rname not in working_constraint:
                    working_constraint[rname] = rvalue
                else:
                    # hit a conflict, so start a new working cons
                    # so we maintain precedence
                    working_constraint = {rname: rvalue}
                    constraints.append(working_constraint)

            queue_constraints = queue.get_non_host_constraints(
                job_resources, node_count
            )
            constraints.extend(queue_constraints)

            job = Job(
                name=my_job_id,
                constraints=constraints,
                iterations=iterations,
                node_count=node_count,
                colocated=colocated,
                packing_strategy=pack,
            )
            job.iterations_remaining = remaining
            ret.append(job)

    return ret


def parse_scheduler_nodes(
    config: Dict,
    pbscmd: PBSCMD,
    resource_definitions: Dict[str, PBSProResourceDefinition],
) -> List[Node]:
    """
    Gets the current state of the nodes as the scheduler sees them, including resources,
    assigned resources, jobs currently running etc.
    """
    ret: List[Node] = []
    ignore_onprem = config.get("pbspro", {}).get("ignore_onprem", False)
    ignore_hostnames_re_expr = config.get("pbspro", {}).get("ignore_hostnames_re")
    ignore_hostnames_re = None
    if ignore_hostnames_re_expr:
        try:
            ignore_hostnames_re = re.compile(ignore_hostnames_re_expr)
        except Exception:
            logging.exception(
                f"Could not parse {ignore_hostnames_re_expr} as a regular expression"
            )
    ignored_hostnames = []

    for ndict in pbscmd.pbsnodes_parsed("-a"):
        if ignore_hostnames_re and ignore_hostnames_re.match(ndict["name"]):
            ignored_hostnames.append(ndict["name"])
            continue

        if ignore_onprem and ndict.get("resources_available.ccnodeid"):
            ignored_hostnames.append(ndict["name"])
            continue

        node = parse_scheduler_node(ndict, resource_definitions)

        if not node.available.get("ccnodeid"):
            node.metadata["override_resources"] = False
            logging.fine(
                "'ccnodeid' is not defined so %s has not been joined to the cluster by the autoscaler"
                + " yet or this is not a CycleCloud managed node",
                node,
            )
        ret.append(node)

    if ignored_hostnames:
        if len(ignored_hostnames) < 5:
            logging.info(
                f"Ignored {len(ignored_hostnames)} hostnames. {','.join(ignored_hostnames)}"
            )
        else:
            logging.info(
                f"Ignored {len(ignored_hostnames)} hostnames. {','.join(ignored_hostnames[:5])}..."
            )
    return ret


def parse_scheduler_node(
    ndict: Dict[str, Any], resource_definitions: Dict[str, PBSProResourceDefinition]
) -> SchedulerNode:
    """
    Implementation of parsing a single scheduler node.
    """
    parser = get_pbspro_parser()

    hostname = ndict["name"]
    res_avail = parser.parse_resources_available(ndict, filter_is_host=True)
    res_assigned = parser.parse_resources_assigned(ndict, filter_is_host=True)

    node = SchedulerNode(hostname, res_avail)
    jobs_expr = ndict.get("jobs", "")

    state = ndict.get("state") or ""

    if state == "free" and jobs_expr.strip():
        state = "partially-free"

    node.metadata["pbs_state"] = state
    # This ends up ignoring KeepAlive, so just let downstream handling of down/offline nodes.
    # if "down" in state:
    #     node.marked_for_deletion = True

    node.metadata["last_state_change_time"] = ndict.get("last_state_change_time", "")

    for tok in jobs_expr.split(","):
        tok = tok.strip()
        if not tok:
            continue
        job_id_full, sub_job_id = tok.rsplit("/", 1)
        sched_host = ""
        if "." in job_id_full:
            job_id, sched_host = job_id_full.split(".", 1)
        else:
            job_id = job_id_full

        node.assign(job_id)
        node.metadata["_running_job_"] = True

        if "job_ids_long" not in node.metadata:
            node.metadata["job_ids_long"] = [job_id_full]
        elif job_id_full not in node.metadata["job_ids_long"]:
            node.metadata["job_ids_long"].append(job_id_full)

    for res_name, value in res_assigned.items():
        resource = resource_definitions.get(res_name)

        if not resource or not resource.is_host:
            continue

        if resource.is_consumable:
            if res_name in node.available:
                node.available[res_name] -= value
            else:
                logging.warning(
                    "%s was not defined under resources_available, but was "
                    + "defined under resources_assigned for %s. Setting available to assigned.",
                    res_name,
                    node,
                )
                node.available[res_name] = value

    if "exclusive" in node.metadata["pbs_state"]:
        node.closed = True

    node.metadata["comment"] = ndict.get("comment", "")

    return node
