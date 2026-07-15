from typing import Any, Dict, List, Optional, Tuple

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
        limits: Optional[List["QueueLimit"]] = None,
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
        self.limits = limits or []
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

            shared_resource_list: List[conslib.SharedResource] = (
                self.resource_state.shared_resources[rname]
            )

            assert (
                shared_resource_list
            ), "Error while processing queue/server resource {}".format(rname)

            if shared_resource_list[0].is_consumable:

                # A queue/server (non-host) consumable is consumed once for the
                # whole job, not once per node. decrement_once ensures the shared
                # value is decremented a single time even when the job spans
                # multiple nodes (which each invoke do_decrement).
                ret.append(
                    conslib.SharedConsumableConstraint(
                        shared_resource_list, rvalue, decrement_once=True
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
            limits=parser.parse_queue_limits(qdict),
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
        limit = 2**31

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


# scope kinds evaluated for every job, in (kind, PBSProLimit-attribute) form.
# "overall" is special-cased because it always resolves against the PBS_ALL key.
_SCOPE_KINDS = ["overall", "user", "group", "project"]


class QueueLimit:
    """
    A single parsed run-limit attribute on a queue.

    resource is None for count limits (max_run, max_running, max_user_run,
    max_group_run) and the resource name (e.g. "ncpus") for resource limits
    (max_run_res.<res>). limit holds the per-scope values.
    """

    def __init__(
        self, source_attr: str, resource: Optional[str], limit: PBSProLimit
    ) -> None:
        self.source_attr = source_attr
        self.resource = resource
        self.limit = limit

    @property
    def is_count(self) -> bool:
        return self.resource is None

    def __repr__(self) -> str:
        return "QueueLimit(attr={}, resource={}, limit={})".format(
            self.source_attr, self.resource, self.limit
        )


class QueueLimitTracker:
    """
    Caps autoscale demand for a queue at each run limit's remaining budget.

    A run limit is modeled as a finite shared pool the jobs draw from, using the
    same SharedConsumableResource / SharedConsumableConstraint machinery already
    used for license-style queue/server resources. The remaining budget for a
    scope is the configured limit minus the amount already consumed by that
    scope's running jobs, so the autoscaler only acquires capacity PBS can
    actually dispatch.

    Distinct scope instances (e.g. two different users under a per-user limit)
    map to distinct pools, so one scope exhausting its budget does not block
    another.
    """

    def __init__(self, queue_name: str, limits: List[QueueLimit]) -> None:
        self.queue_name = queue_name
        self.limits = limits
        # running usage keyed by (scope_kind, scope_name, resource_or_None).
        # resource_or_None is None for the running-job count.
        self._usage: Dict[Tuple[str, str, Optional[str]], float] = {}
        # pools shared across all jobs, keyed by
        # (source_attr, scope_kind, scope_name, resource_or_None).
        self._pools: Dict[
            Tuple[str, str, str, Optional[str]], conslib.SharedConsumableResource
        ] = {}

    @property
    def active(self) -> bool:
        return bool(self.limits)

    def add_running_usage(
        self,
        user: Optional[str],
        group: Optional[str],
        project: Optional[str],
        resources: Dict[str, Any],
    ) -> None:
        """Accumulate a running job's contribution to per-scope usage."""
        for scope_kind, scope_name in self._scopes(user, group, project):
            count_key: Tuple[str, str, Optional[str]] = (scope_kind, scope_name, None)
            self._usage[count_key] = self._usage.get(count_key, 0) + 1

            for res_name, amount in resources.items():
                if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                    continue
                res_key: Tuple[str, str, Optional[str]] = (
                    scope_kind,
                    scope_name,
                    res_name,
                )
                self._usage[res_key] = self._usage.get(res_key, 0) + amount

    def get_constraints(
        self,
        user: Optional[str],
        group: Optional[str],
        project: Optional[str],
        resources: Dict[str, Any],
    ) -> List[conslib.NodeConstraint]:
        """
        Build the shared-consumable constraints that cap a queued job's demand.

        resources must be the job's total requested resources (Resource_List),
        so a resource limit consumes the job's whole request the way PBS accounts
        the equivalent regular resource.
        """
        ret: List[conslib.NodeConstraint] = []

        for queue_limit in self.limits:
            for scope_kind, scope_name in self._scopes(user, group, project):
                limit_value = self._scope_limit(
                    queue_limit.limit, scope_kind, scope_name
                )
                if limit_value is None:
                    # this scope is not limited (no specific nor PBS_GENERIC entry)
                    continue

                if queue_limit.is_count:
                    amount: float = 1
                else:
                    amount = resources.get(queue_limit.resource)  # type: ignore
                    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                        continue
                    if amount <= 0:
                        continue

                pool = self._get_pool(queue_limit, scope_kind, scope_name, limit_value)
                ret.append(
                    conslib.SharedConsumableConstraint(
                        [pool], amount, decrement_once=True
                    )
                )

        return ret

    def _scopes(
        self, user: Optional[str], group: Optional[str], project: Optional[str]
    ) -> List[Tuple[str, str]]:
        scope_values = {
            "overall": "PBS_ALL",
            "user": user,
            "group": group,
            "project": project,
        }
        return [
            (kind, scope_values[kind]) for kind in _SCOPE_KINDS if scope_values[kind]
        ]

    @staticmethod
    def _scope_limit(
        limit: PBSProLimit, scope_kind: str, scope_name: str
    ) -> Optional[int]:
        if scope_kind == "overall":
            return limit.overall.get("PBS_ALL")

        table: Dict[str, int] = getattr(limit, scope_kind)
        if scope_name in table:
            return table[scope_name]
        return table.get("PBS_GENERIC")

    def _get_pool(
        self,
        queue_limit: QueueLimit,
        scope_kind: str,
        scope_name: str,
        limit_value: int,
    ) -> conslib.SharedConsumableResource:
        pool_key = (
            queue_limit.source_attr,
            scope_kind,
            scope_name,
            queue_limit.resource,
        )
        pool = self._pools.get(pool_key)
        if pool is None:
            usage = self._usage.get((scope_kind, scope_name, queue_limit.resource), 0)
            remaining = max(0, limit_value - usage)
            name = "__run_limit__{}__{}__{}__{}__{}".format(
                self.queue_name,
                queue_limit.source_attr,
                scope_kind,
                scope_name,
                queue_limit.resource or "count",
            )
            source = "queue[{}].{}".format(self.queue_name, queue_limit.source_attr)
            pool = conslib.SharedConsumableResource(name, source, remaining, remaining)
            self._pools[pool_key] = pool
        return pool
