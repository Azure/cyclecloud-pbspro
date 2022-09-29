from typing import Any, Dict, List, Optional

import typing_extensions
from hpc.autoscale.node import constraints as conslib

from pbspro.parser import get_pbspro_parser
from pbspro.pbscmd import PBSCMD
from pbspro.resource import PBSProResourceDefinition, ResourceState
from pbspro.util import filter_non_host_resources

StateCountType = typing_extensions.Literal[
    "Transit", "Queued", "Held", "Waiting", "Running", "Exiting", "Begun"
]

StateCounts = [
    "Transit",
    "Queued",
    "Held",
    "Waiting",
    "Running",
    "Exiting",
    "Begun",
]


class PBSProQueue:
    def __init__(
        self,
        name: str,
        queue_type: str,
        node_group_key: Optional[str],
        node_group_enable: bool,
        total_jobs: int,
        state_count: Dict[StateCountType, int],
        resources_default: Dict[str, str],
        default_chunk: Dict[str, str],
        resource_state: ResourceState,
        resource_definitions: Dict[str, PBSProResourceDefinition],
        enabled: bool,
        started: bool,
    ) -> None:
        """{
            "type": "Queue",
            "name": "workq",
            "queue_type": "Execution",
            "total_jobs": "0",
            "state_count": "Transit:0 Queued:0 Held:0 Waiting:0 Running:0 Exiting:0 Begun:0",
            "resources_default.place": "scatter",
            "enabled": "True",
            "started": "True",
        },"""
        self.name = name
        self.queue_type = queue_type
        self.node_group_key = node_group_key
        self.node_group_enable = node_group_enable
        self.total_jobs = total_jobs
        self.state_count = state_count
        self.resources_default = resources_default
        self.default_chunk = default_chunk
        self.enabled = enabled
        self.started = started
        self.resource_state = resource_state
        self.__resource_definitions = filter_non_host_resources(resource_definitions)

    @property
    def uses_placement(self) -> bool:
        """
        This setting is actually on the server, s
        """
        return not bool(self.node_group_key)

    @property
    def transit(self) -> int:
        return self.state_count.get("Transit", 0)

    @property
    def queued(self) -> int:
        return self.state_count.get("Queued", 0)

    @property
    def held(self) -> int:
        return self.state_count.get("Held", 0)

    @property
    def waiting(self) -> int:
        return self.state_count.get("Waiting", 0)

    @property
    def running(self) -> int:
        return self.state_count.get("Running", 0)

    @property
    def exiting(self) -> int:
        return self.state_count.get("Exiting", 0)

    @property
    def begun(self) -> int:
        return self.state_count.get("Begun", 0)

    def get_non_host_constraints(
        self, pbs_resources: Dict[str, Any], nodect: int
    ) -> List[conslib.NodeConstraint]:
        ret: List[conslib.NodeConstraint] = []

        for rname, rvalue in pbs_resources.items():
            resource = self.__resource_definitions.get(rname)

            if not resource:
                continue

            if resource.is_host:
                continue

            if rname not in self.resource_state.shared_resources:
                raise RuntimeError(
                    f"Undefined resource {rname}. Is this a misconfigured server_dyn_res?"
                )

            shared_resource_list: List[
                conslib.SharedResource
            ] = self.resource_state.shared_resources[rname]

            assert (
                shared_resource_list
            ), "Error while processing queue/server resource {}".format(rname)

            if shared_resource_list[0].is_consumable:

                ret.append(
                    conslib.SharedConsumableConstraint(
                        shared_resource_list, rvalue / nodect
                    )
                )
            else:
                ret.append(
                    conslib.SharedNonConsumableConstraint(
                        shared_resource_list[0], rvalue
                    )
                )
        return ret

    def __repr__(self) -> str:
        return "Queue(name={}, running={}, queued={}, total={})".format(
            self.name,
            self.state_count.get("Running"),
            self.state_count.get("Queued"),
            self.total_jobs,
        )


def list_queue_names(pbscmd: PBSCMD) -> List[str]:
    ret = []

    lines_less_header = pbscmd.qstat("-Q").splitlines()[1:]
    for line in lines_less_header:
        line = line.strip()

        if not line:
            continue

        if line.startswith("---"):
            continue

        qname = line.split()[0]
        ret.append(qname)

    return ret


def read_queues(
    config: Dict,
    pbscmd: PBSCMD,
    resource_definitions: Dict[str, PBSProResourceDefinition],
    scheduler_shared_resources: Dict[str, conslib.SharedResource],
) -> Dict[str, PBSProQueue]:
    parser = get_pbspro_parser()

    ret: Dict[str, PBSProQueue] = {}
    qnames = list_queue_names(pbscmd)
    queue_dicts = pbscmd.qmgr_parsed("list", "queue", ",".join(qnames))

    # queue resources will include things like ncpus - i.e. the total amount of ncpus etc
    # They are meaningless as a shared constraint, they are only there for info purposes
    ignore_queues = config.get("pbspro", {}).get("ignore_queues", [])

    for qdict in queue_dicts:
        state_count = parser.parse_state_counts(qdict["state_count"])

        resource_state = parser.parse_resource_state(qdict, scheduler_shared_resources)

        queue = PBSProQueue(
            name=qdict["name"],
            queue_type=qdict["queue_type"],
            node_group_key=qdict.get("node_group_key"),
            node_group_enable=qdict.get("node_group_enable", "").lower() == "true",
            total_jobs=int(qdict["total_jobs"]),
            state_count=state_count,
            resource_state=resource_state,
            resources_default=parser.parse_resources_default(qdict),
            default_chunk=parser.parse_default_chunk(qdict),
            resource_definitions=resource_definitions,
            enabled=qdict["enabled"].lower() == "true"
            and qdict["name"] not in ignore_queues,
            started=qdict["started"].lower() == "true",
        )
        ret[queue.name] = queue

    return ret


class PBSProLimit:
    def __init__(self) -> None:
        self.overall: Dict[str, int] = {}
        self.project: Dict[str, int] = {}
        self.group: Dict[str, int] = {}
        self.user: Dict[str, int] = {}

    def get_limit(
        self,
        user: Optional[str] = None,
        groups: Optional[List[str]] = None,
        project: Optional[str] = None,
    ) -> int:
        groups = groups or []
        limit = 2 ** 31

        if "PBS_ALL" in self.overall:
            limit = min(limit, self.overall["PBS_ALL"])

        if groups:
            group_limit = 0
            for group in groups:
                group_limit += self.group.get(group, self.group.get("PBS_GENERIC", 0))
            limit = min(limit, group_limit)

        if user:
            user_limit = self.user.get(user, self.user.get("PBS_GENERIC"))
            if user_limit is not None:
                limit = min(limit, user_limit)

        if project:
            project_limit = self.project.get(project, self.project.get("PBS_GENERIC"))
            if project_limit is not None:
                limit = min(limit, project_limit)

        return limit

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PBSProLimit):
            return False
        o: PBSProLimit = other

        if self.overall != o.overall:
            return False

        if self.project != o.project:
            return False

        if self.group != o.group:
            return False

        if self.user != o.user:
            return False

        return True

    def __repr__(self) -> str:
        return str(
            {
                "overall": self.overall,
                "project": self.project,
                "group": self.group,
                "user": self.user,
            }
        )
