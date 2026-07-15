import datetime
import time
from typing import Any, Dict, List

import pytest
from hpc.autoscale import util
from hpc.autoscale.ccbindings.mock import MockClusterBinding
from hpc.autoscale.job.demandcalculator import new_demand_calculator
from hpc.autoscale.job.schedulernode import SchedulerNode
from hpc.autoscale.node.nodehistory import NullNodeHistory

from pbspro.constants import PBSProJobStates
from pbspro.driver import PBSProDriver, parse_jobs, parse_scheduler_node
from pbspro.parser import PBSProParser, get_pbspro_parser, set_pbspro_parser
from pbspro.pbsqueue import PBSProQueue
from pbspro.resource import (
    BooleanType,
    LongType,
    PBSProResourceDefinition,
    ResourceState,
    StringType,
)


def setup_module() -> None:
    SchedulerNode.ignore_hostnames = True
    resource_defs = {
        "ncpus": PBSProResourceDefinition("ncpus", LongType(), "nh"),
        "group_id": PBSProResourceDefinition("group_id", StringType(), "h"),
        "infiniband": PBSProResourceDefinition("infiniband", BooleanType(), "h"),
    }

    set_pbspro_parser(PBSProParser(resource_defs))


def teardown_module() -> None:
    set_pbspro_parser(None)


def test_parse_scheduler_node() -> None:
    actual = parse_scheduler_node(
        {
            "name": "tux",
            "resources_available.ncpus": 4,
            "resources_available.group_id": "pg0",
            "resources_available.infiniband": True,
            "resources_assigned.ncpus": 3,
            "resources_assigned.group_id": "pg0",
            "resources_assigned.infiniband": True,
        },
        get_pbspro_parser().resource_definitions,
    )

    expected = SchedulerNode("tux", {"ncpus": 4, "group_id": "pg0", "infiniband": True})
    expected.available["ncpus"] = 1

    assert expected.hostname == actual.hostname
    assert expected.resources == actual.resources
    assert expected.available == actual.available


def test_down_long_enough() -> None:
    node = SchedulerNode("localhost", {})
    now = datetime.datetime.now()

    # False: missing last_state_change_time
    driver = PBSProDriver({}, down_timeout=300)
    assert not driver._down_long_enough(now, node)

    # False: last_state_change_time < 300 seconds ago
    last_state_change_time = now - datetime.timedelta(seconds=1)
    node.metadata["last_state_change_time"] = datetime.datetime.ctime(
        last_state_change_time
    )
    assert not driver._down_long_enough(now, node)

    # True: last_state_change_time > 300 seconds ago
    last_state_change_time = now - datetime.timedelta(seconds=301)
    node.metadata["last_state_change_time"] = datetime.datetime.ctime(
        last_state_change_time
    )
    assert driver._down_long_enough(now, node)


def _pbs_job(
    queue: str = "workq",
    job_state: str = PBSProJobStates.Queued,
    array_indices_remaining: int = -1,
    array_indices_submitted: int = -1,
    resource_list: Dict[str, Any] = {},
    nodect: int = 1,
) -> Dict[str, Any]:

    jdict: Dict[str, Any] = {
        "job_state": job_state,
        "queue": queue,
        "nodect": nodect,
    }

    if array_indices_submitted > 0:
        jdict["array"] = True
        jdict["array_indices_remaining"] = array_indices_remaining
        jdict["array_indices_submitted"] = array_indices_submitted

    jdict["Resource_List"] = resource_list

    return jdict


@pytest.mark.skip
def test_git_submodule() -> None:
    assert False, "fix git submodule"


# ---------------------------------------------------------------------------
# Autoscale demand with queue run limits (parse_jobs end-to-end)
# ---------------------------------------------------------------------------


class _FakePBSCMD:
    def __init__(self, response: Dict[str, Any]) -> None:
        self._response = response

    def qstat_json(self, *args: str) -> Dict[str, Any]:
        return self._response


def _make_queue(name: str, limits: Any = None) -> PBSProQueue:
    return PBSProQueue(
        name=name,
        queue_type="execution",
        node_group_key="group_id",
        node_group_enable=True,
        total_jobs=0,
        state_count={},
        resources_default={"place": "free", "ungrouped": "true"},
        default_chunk={"place": "free", "ungrouped": "true"},
        resource_state=ResourceState(
            resources_available={}, resources_assigned={}, shared_resources={}
        ),
        resource_definitions=get_pbspro_parser().resource_definitions,
        enabled=True,
        started=True,
        limits=limits,
    )


def _job(user: str, ncpus: int, state: str, queue: str = "long") -> Dict[str, Any]:
    return {
        "job_state": state,
        "queue": queue,
        "euser": user,
        "schedselect": "1:ncpus={}".format(ncpus),
        "Resource_List": {"ncpus": ncpus, "place": "free", "nodect": 1},
    }


def _demand_for(
    jobs: List[Dict[str, Any]],
    queues: Dict[str, PBSProQueue],
    per_node_ncpus: int,
) -> Any:
    response = {"Jobs": {"job-{}".format(i): j for i, j in enumerate(jobs)}}
    pbscmd = _FakePBSCMD(response)
    parsed = parse_jobs(
        pbscmd, get_pbspro_parser().resource_definitions, queues, {"ncpus"}
    )

    bindings = MockClusterBinding()
    bindings.add_nodearray("execute", {"ncpus": per_node_ncpus})
    bindings.add_bucket("execute", "Standard_F2", 100, 100)
    dc = new_demand_calculator(
        config={"_mock_bindings": bindings},
        existing_nodes=[],
        node_history=NullNodeHistory(),
        singleton_lock=util.NullSingletonLock(),
    )
    dc.add_jobs(parsed)
    return dc.get_demand()


def test_autoscale_caps_nodes_at_remaining_ncpus_budget() -> None:
    parser = get_pbspro_parser()
    queues = {
        "long": _make_queue(
            "long",
            parser.parse_queue_limits({"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"}),
        )
    }
    jobs: List[Dict[str, Any]] = []
    # alice already running 800 ncpus (8 x 100)
    for _ in range(8):
        jobs.append(_job("alice", 100, PBSProJobStates.Running))
    # many queued alice jobs, each needing 100 ncpus
    for _ in range(10):
        jobs.append(_job("alice", 100, PBSProJobStates.Queued))

    demand = _demand_for(jobs, queues, per_node_ncpus=100)
    # remaining budget is 400 ncpus -> at most 4 additional nodes.
    assert len(demand.new_nodes) == 4


def test_autoscale_acquires_nothing_when_budget_exhausted() -> None:
    parser = get_pbspro_parser()
    queues = {
        "long": _make_queue(
            "long",
            parser.parse_queue_limits({"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"}),
        )
    }
    jobs: List[Dict[str, Any]] = []
    # alice already running 1200 ncpus (budget exhausted)
    for _ in range(12):
        jobs.append(_job("alice", 100, PBSProJobStates.Running))
    for _ in range(5):
        jobs.append(_job("alice", 100, PBSProJobStates.Queued))

    demand = _demand_for(jobs, queues, per_node_ncpus=100)
    assert len(demand.new_nodes) == 0


def test_autoscale_unlimited_queue_is_unchanged() -> None:
    # a queue with no run limits places every queued job as before.
    queues = {"long": _make_queue("long", None)}
    jobs = [_job("alice", 100, PBSProJobStates.Queued) for _ in range(5)]

    demand = _demand_for(jobs, queues, per_node_ncpus=100)
    assert len(demand.new_nodes) == 5


def test_autoscale_limit_on_one_user_does_not_block_another() -> None:
    parser = get_pbspro_parser()
    queues = {
        "long": _make_queue(
            "long",
            parser.parse_queue_limits({"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"}),
        )
    }
    jobs: List[Dict[str, Any]] = []
    # alice's budget is exhausted...
    for _ in range(12):
        jobs.append(_job("alice", 100, PBSProJobStates.Running))
    # ...bob has full budget remaining.
    for _ in range(3):
        jobs.append(_job("alice", 100, PBSProJobStates.Queued))
    for _ in range(4):
        jobs.append(_job("bob", 100, PBSProJobStates.Queued))

    demand = _demand_for(jobs, queues, per_node_ncpus=100)
    # only bob's 4 jobs drive node acquisition.
    assert len(demand.new_nodes) == 4


def test_autoscale_array_partially_satisfied_within_budget() -> None:
    # qstat -f -t expands an array into independent subjobs; each is evaluated
    # against the remaining budget, so an array is partially satisfied.
    parser = get_pbspro_parser()
    queues = {
        "long": _make_queue(
            "long",
            parser.parse_queue_limits({"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"}),
        )
    }
    jobs: List[Dict[str, Any]] = []
    # alice already running 1000 ncpus -> remaining budget 200.
    for _ in range(10):
        jobs.append(_job("alice", 100, PBSProJobStates.Running))
    # a queued array of 10 subjobs, each needing 100 ncpus.
    for _ in range(10):
        jobs.append(_job("alice", 100, PBSProJobStates.Queued))

    demand = _demand_for(jobs, queues, per_node_ncpus=100)
    # only 2 subjobs (200 ncpus) fit; the other 8 are not placed.
    assert len(demand.new_nodes) == 2
