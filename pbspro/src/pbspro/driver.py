from subprocess import CalledProcessError, SubprocessError
from typing import Any, Dict, List, Optional, Set, Tuple

from hpc.autoscale import hpclogging as logging
from hpc.autoscale import hpctypes as ht
from hpc.autoscale.job.job import Job, PackingStrategy
from hpc.autoscale.job.nodequeue import NodeQueue
from hpc.autoscale.job.schedulernode import SchedulerNode
from hpc.autoscale.node.constraints import SharedResource
from hpc.autoscale.node.node import Node
from hpc.autoscale.results import EarlyBailoutResult
from hpc.autoscale.job.driver import SchedulerDriver


from pbspro.constants import PBSProJobStates
from pbspro.parser import get_pbspro_parser
from pbspro.pbscmd import PBSCMD
from pbspro.queue import PBSProQueue, read_queues
from pbspro.resource import PBSProResourceDefinition
from pbspro.scheduler import PBSProScheduler, read_schedulers
from functools import lru_cache
from hpc.autoscale.node.nodemanager import NodeManager
from numbers import Number


# sched_config = "/var/spool/pbs/sched_priv/sched_config"


class PBSEnvironmentError(RuntimeError):
    ...


class PBSProDriver(SchedulerDriver):
    def __init__(
        self,
        pbscmd: Optional[PBSCMD] = None,
        resource_definitions: Optional[Dict[str, PBSProResourceDefinition]] = None,
    ) -> None:
        super().__init__("pbspro")
        self.pbscmd = pbscmd or PBSCMD(get_pbspro_parser())
        self.__queues: Optional[Dict[str, PBSProQueue]] = None
        self.__shared_resources: Optional[Dict[str, SharedResource]]
        self.__resource_definitions = resource_definitions
        self.__read_only_resources: Optional[Set[str]] = None

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
        # TODO RDH maybe add default resource for ccnodeid?
        return config

    def preprocess_node_mgr(self, config: Dict, node_mgr: NodeManager) -> None:
        super().preprocess_node_mgr(config, node_mgr)
        node_mgr.add_default_resource({}, "group_id", "node.placement_group")

    def handle_failed_nodes(self, nodes: List[Node]) -> List[Node]:
        return []

    def add_nodes_to_cluster(self, nodes: List[Node]) -> List[Node]:
        self.initialize()

        ret = []
        for node in nodes:
            if not node.resources.get("ccnodeid"):
                logging.info(
                    "%s is not managed by CycleCloud, or at least 'ccnodeid' is not defined. Ignoring",
                    node,
                )
                continue
            try:
                try:
                    ndicts = self.pbscmd.qmgr_parsed("list", "node", node.hostname)
                    if ndicts and ndicts[0].get("ccnodeid"):
                        logging.info(
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

                    # skip things like host which are useful to set default resources on non-existent
                    # nodes for autoscale packing, but not on actual nodes
                    if res_name in self.read_only_resources:
                        continue

                    if res_name not in self.resource_definitions:
                        # TODO RDH add warning
                        continue
                    res_value_str: str

                    # pbs size does not support decimals
                    if isinstance(res_value, ht.Size):
                        res_value_str = "{}{}".format(
                            int(res_value.value), res_value.magnitude
                        )
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
                self.pbscmd.pbsnodes("-r", node.hostname)
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
        return nodes

    def handle_draining(self, nodes: List[Node]) -> List[Node]:
        # TODO RDH batch these up, but keep it underneath the
        # max arg limit
        ret = []
        for node in nodes:
            if not node.hostname:
                logging.info("Node %s has no hostname.", node)
                continue

            # TODO RDH implement after we have resources added back in
            # if not node.resources.get("ccnodeid"):
            #     continue

            if "offline" in node.metadata.get("pbs_state", ""):
                if node.assignments:
                    logging.info("Node %s has jobs still running on it.", node)
                    # node is already 'offline' i.e. draining, but a job is still running
                    continue
                else:
                    # ok - it is offline _and_ no jobs are running on it.
                    ret.append(node)
            else:
                try:
                    self.pbscmd.pbsnodes("-o", node.hostname)
                except CalledProcessError as e:
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
                self.pbscmd.qmgr("delete", "node", node.hostname)
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
                self.pbscmd, self.resource_definitions, shared_resources
            )
        assert shared_resources == self.__shared_resources
        return self.__queues

    def parse_jobs(
        self,
        queues: Dict[str, PBSProQueue],
        resources_for_scheduling: Set[str],
    ) -> List[Job]:
        return parse_jobs(
            self.pbscmd, self.resource_definitions, queues, resources_for_scheduling
        )

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

    def parse_scheduler_nodes(
        self,
    ) -> List[Node]:
        return parse_scheduler_nodes(self.pbscmd, self.resource_definitions)


class PBSProNodeQueue(NodeQueue):
    def early_bailout(self, node: Node) -> EarlyBailoutResult:
        # TODO RDH if ncpus == 0
        # not great if jobs use n-1 ncpus...
        return super().early_bailout(node)


def parse_jobs(
    pbscmd: PBSCMD,
    resource_definitions: Dict[str, PBSProResourceDefinition],
    queues: Dict[str, PBSProQueue],
    resources_for_scheduling: Set[str],
) -> List[Job]:
    """
    TODO RDH
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

        if jdict.get("array"):
            iterations = parser.parse_range_size(jdict["array_indices_submitted"])
            remaining = parser.parse_range_size(jdict["array_indices_remaining"])
        elif "[" in job_id:
            continue
        else:
            iterations = 1
            remaining = 1

        res_list = jdict["Resource_List"]
        rdict = parser.convert_resource_list(res_list)

        pack = (
            PackingStrategy.PACK
            if rdict["place"]["arrangement"] in ["free", "pack"]
            else PackingStrategy.SCATTER
        )

        colocated = rdict["place"].get("grouping") == "group=group_id"

        # pack jobs do not need to define node_count
        node_count = 0
        if pack == PackingStrategy.SCATTER or is_smp:
            print("RDH", rdict)
            node_count = int(rdict["nodect"])

        # SMP style jobs
        is_smp = rdict["place"].get("grouping") == "host"

        sharing = rdict["place"].get("sharing")

        for n, chunk_base in enumerate(rdict["select"]):
            chunk: Dict[str, Any] = {}
            chunk.update(rdict)
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
            if len(rdict["select"]) > 1:
                if "." in job_id:
                    job_index, host = job_id.split(".", 1)
                    my_job_id = "{}+{}.{}".format(job_index, n, host)
                else:
                    my_job_id = "{}+{}".format(job_id, n)

            if sharing == "excl":
                working_constraint["exclusive-task"] = True
            elif sharing == "exclhost":
                # TODO RDH
                logging.warning("exclhost is not supported at this moment. Skipping")
                continue
                # constraints.append({"exclusive": True})

            job_resources = {}

            for rname, rvalue in chunk.items():
                if rname in ["select", "place", "nodect"]:
                    continue

                if rname not in resources_for_scheduling:
                    # TODO RDH
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

            qname = jdict.get("queue")
            if not qname or qname not in queues:
                logging.warning("queue was not defined for job %s: ignoring", job_id)
                continue

            queue: PBSProQueue = queues[qname]
            queue_constraints = queue.get_non_host_constraints(job_resources)
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
    pbscmd: PBSCMD, resource_definitions: Dict[str, PBSProResourceDefinition]
) -> List[Node]:
    """
    TODO RDH
    """
    ret: List[Node] = []
    for ndict in pbscmd.pbsnodes_parsed("-a"):
        ret.append(parse_scheduler_node(ndict, resource_definitions))
    return ret


def parse_scheduler_node(
    ndict: Dict[str, Any], resource_definitions: Dict[str, PBSProResourceDefinition]
) -> SchedulerNode:
    """
    TODO RDH
    """
    parser = get_pbspro_parser()

    hostname = ndict["name"]
    res_avail = parser.parse_resources_available(ndict, filter_is_host=True)
    res_assigned = parser.parse_resources_assigned(ndict, filter_is_host=True)

    node = SchedulerNode(hostname, res_avail)

    node.metadata["pbs_state"] = ndict.get("state")

    jobs_expr = ndict.get("jobs", "")

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

    return node
