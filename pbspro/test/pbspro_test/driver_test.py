import datetime
import time
from typing import Any, Dict

import pytest
from hpc.autoscale.job.schedulernode import SchedulerNode

from pbspro.constants import PBSProJobStates
from pbspro.driver import PBSProDriver, parse_scheduler_node
from pbspro.parser import PBSProParser, get_pbspro_parser, set_pbspro_parser
from pbspro.resource import BooleanType, LongType, PBSProResourceDefinition, StringType


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
