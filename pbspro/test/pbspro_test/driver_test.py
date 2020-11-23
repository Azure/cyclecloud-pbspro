from hpc.autoscale.job.schedulernode import SchedulerNode

from pbspro.driver import parse_scheduler_node
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


def test_git_submodule() -> None:
    assert False, "fix git submodule"