import typing
from typing import Dict

if typing.TYPE_CHECKING:
    from pbspro.resource import PBSProResourceDefinition  # noqa: F401


def filter_host_resources(
    resource_definitions: Dict[str, "PBSProResourceDefinition"]
) -> Dict[str, "PBSProResourceDefinition"]:
    return dict([(k, v) for k, v in resource_definitions.items() if v.is_host])


def filter_non_host_resources(
    resource_definitions: Dict[str, "PBSProResourceDefinition"]
) -> Dict[str, "PBSProResourceDefinition"]:
    return dict([(k, v) for k, v in resource_definitions.items() if not v.is_host])
