import pytest

from pbspro.parser import PBSProParser
from pbspro.resource import RESOURCE_TYPES, PBSProResourceDefinition


@pytest.fixture
def parser() -> PBSProParser:
    return PBSProParser(
        {
            "abc": PBSProResourceDefinition("abc", RESOURCE_TYPES["boolean"], "h"),
            "qres": PBSProResourceDefinition("qres", RESOURCE_TYPES["long"], "q"),
            "ncpus": PBSProResourceDefinition("ncpus", RESOURCE_TYPES["long"], "nh"),
        }
    )
