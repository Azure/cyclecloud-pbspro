from typing import Dict

import pytest

from pbspro.parser import PBSProParser
from pbspro.pbsqueue import PBSProQueue
from pbspro.resource import RESOURCE_TYPES, PBSProResourceDefinition, ResourceState


@pytest.fixture
def parser() -> PBSProParser:
    return PBSProParser(
        {
            "abc": PBSProResourceDefinition("abc", RESOURCE_TYPES["boolean"], "h"),
            "qres": PBSProResourceDefinition("qres", RESOURCE_TYPES["long"], "q"),
            "ncpus": PBSProResourceDefinition("ncpus", RESOURCE_TYPES["long"], "nh"),
        }
    )


@pytest.fixture
def queues(parser: PBSProParser) -> Dict[str, PBSProQueue]:
    resource_state = ResourceState(
        resources_available={}, resources_assigned={}, shared_resources={}
    )
    return {
        "workq": PBSProQueue(
            name="workq",
            queue_type="execution",
            node_group_enable=True,
            node_group_key="group_id",
            default_chunk={"place": "scatter:excl", "ungrouped": "false"},
            enabled=True,
            resource_state=resource_state,
            resources_default={"place": "scatter:excl", "ungrouped": "false"},
            resource_definitions=parser.resource_definitions,
            started=True,
            state_count={},
            total_jobs=0,
        ),
        "htcq": PBSProQueue(
            name="htcq",
            queue_type="execution",
            node_group_enable=True,
            node_group_key="group_id",
            default_chunk={"place": "free", "ungrouped": "true"},
            enabled=True,
            resource_state=resource_state,
            resources_default={"place": "free", "ungrouped": "true"},
            resource_definitions=parser.resource_definitions,
            started=True,
            state_count={},
            total_jobs=0,
        ),
    }
