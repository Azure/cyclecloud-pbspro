import os
from abc import abstractmethod
from subprocess import CalledProcessError
from typing import Any, Dict, List

import typing_extensions
from hpc.autoscale import hpclogging as logging
from hpc.autoscale.hpctypes import Size as HPCSize
from hpc.autoscale.hpctypes import add_magnitude_conversion
from hpc.autoscale.node.constraints import SharedResource

from pbspro.pbscmd import PBSCMD

add_magnitude_conversion("w", 8)
add_magnitude_conversion("kb", 1 * 1024)
add_magnitude_conversion("kw", 8 * 1024)
add_magnitude_conversion("mb", 1 * (1024 ** 2))
add_magnitude_conversion("mw", 8 * (1024 ** 2))
add_magnitude_conversion("gb", 1 * (1024 ** 3))
add_magnitude_conversion("gw", 8 * (1024 ** 3))
add_magnitude_conversion("tb", 1 * (1024 ** 4))
add_magnitude_conversion("tw", 8 * (1024 ** 4))
add_magnitude_conversion("pb", 1 * (1024 ** 5))
add_magnitude_conversion("pw", 8 * (1024 ** 5))


# fmt: off
ResourceFlag = typing_extensions.Literal[
    "",    # non-consumable queue or server level
    "fh",  # consumable on the first host
    "h",   # non-consumable host
    "nh",  # consumable host
    "q",   # consumable at queue or server
]

ResourceFlagNames = ["", "fh", "h", "nh", "q"]
ResourceTypeNames = typing_extensions.Literal["boolean", "duration"]


class ResourceParsingError(RuntimeError):
    pass


class ResourceType:
    def __init__(self) -> None:
        self.name = self.__class__.__name__.replace("Type", "").lower()

    @abstractmethod
    def parse(self, expr: str) -> Any:
        ...

    def __repr__(self) -> str:
        return self.__class__.__name__


VALID_TRUE = ["TRUE", "True", "true", "T", "t", "Y", "y", "1"]
VALID_FALSE = ["FALSE", "False", "false", "F", "f", "N", "n", "0"]


class BooleanType(ResourceType):
    def parse(self, expr: str) -> Any:
        """
        TRUE, True, true, T, t, Y, y, 1
        FALSE, False, false, F, f, N, n, 0
        """

        expr = str(expr)  # in case an int etc gets passed in
        if expr in VALID_TRUE:
            return True

        if expr in VALID_FALSE:
            return False

        raise ResourceParsingError(
            "Could not parse '{}' as a boolean. Expected one of {} or {}",
            expr,
            VALID_TRUE,
            VALID_FALSE,
        )


class DurationType(ResourceType):
    def parse(self, expr: str) -> Any:
        """
        Duration
            A period of time, expressed either as
                An integer whose units are seconds
            or
                [[hours:]minutes:]seconds[.milliseconds]
                in the form:
                    [[HH:]MM:]SS[.milliseconds]
                Milliseconds are rounded to the nearest second.
        """
        try:
            return int(expr)
        except ValueError:
            pass

        def _parse_int(e: str) -> int:
            try:
                return int(e)
            except ValueError:
                raise ResourceParsingError("Could not parse {} as an int".format(e))

        toks = expr.split(":")
        # I'll just always add a milliseconds here
        if "." in toks[-1]:
            toks = toks[:-1] + toks[-1].split(".")
        else:
            toks = toks + ["0"]

        if len(toks) > 4:
            raise ResourceParsingError(
                "Too many fields ({} > 4): Could not parse duration '{}': expected [[hours:]minutes:]seconds[.milliseconds]".format(
                    len(toks), expr
                )
            )

        # weird... I guess I'll handle rounding myself
        # >>> round(.5)
        #    0
        rounded_ms = 1 if _parse_int(toks[-1][0]) >= 5 else 0

        seconds = _parse_int(toks[-2]) + rounded_ms

        if len(toks) >= 3:
            seconds += _parse_int(toks[-3]) * 60

        if len(toks) == 4:
            seconds += _parse_int(toks[-4]) * 60 * 60

        return seconds


class FloatType(ResourceType):
    def parse(self, expr: str) -> Any:
        try:
            return float(expr)
        except ValueError:
            raise ResourceParsingError("Could not parse '{}' as a float".format(expr))


class LongType(ResourceType):
    def parse(self, expr: str) -> Any:
        try:
            return int(expr)
        except ValueError:
            raise ResourceParsingError("Could not parse '{}' as an int".format(expr))


class SizeType(ResourceType):
    def parse(self, expr: str) -> Any:
        try:
            return HPCSize.value_of(expr)
        except Exception:
            raise ResourceParsingError(
                "Could not parse '{}' as type size (e.g. 1mb)".format(expr)
            )


class StringType(ResourceType):
    def parse(self, expr: str) -> Any:
        return str(expr)


class StringArrayType(ResourceType):
    def parse(self, expr: str) -> Any:
        expr = str(expr)
        return [x.strip() for x in expr.split(",")]


RESOURCE_TYPES: Dict[str, "ResourceType"] = {
    "boolean": BooleanType(),
    "duration": DurationType(),
    "float": FloatType(),
    "long": LongType(),
    "size": SizeType(),
    "string": StringType(),
    "string_array": StringArrayType(),
}


def read_resource_definitions(
    pbscmd: PBSCMD, config: Dict
) -> Dict[str, "PBSProResourceDefinition"]:
    ret: Dict[str, PBSProResourceDefinition] = {}
    res_dicts = pbscmd.qmgr_parsed("list", "resource")

    res_names = set([x["name"] for x in res_dicts])

    # TODO I believe this is the only one, but leaving a config option
    # as a backup plan
    read_only = config.get("pbspro", {}).get("read_only_resources", ["host", "vnode"])

    def_sched = pbscmd.qmgr_parsed("list", "sched", "default")
    sched_priv = def_sched[0]["sched_priv"]
    sched_config = os.path.join(sched_priv, "sched_config")
    from pbspro.parser import PBSProParser

    parser = PBSProParser(config)
    sched_resources = parser.parse_resources_from_sched_priv(sched_config)

    missing_res = sched_resources - res_names
    missing_res_dicts = []
    for res_name in missing_res:
        try:
            missing_res_dicts.extend(pbscmd.qmgr_parsed("list", "resource", res_name))
        except CalledProcessError as e:
            logging.warning(
                "Could not find resource %s that was defined in %s, Ignoring",
                res_name,
                sched_config,
            )
            logging.fine(e)

    for rdict in res_dicts + missing_res_dicts:
        name = rdict["name"]
        res_type = RESOURCE_TYPES[rdict["type"]]
        flag: ResourceFlag = rdict.get("flag", "")  # type: ignore
        ret[name] = PBSProResourceDefinition(name, res_type, flag)
        if name in read_only:
            ret[name].read_only = True

    return ret


class PBSProResourceDefinition:
    """Resource slot_type
    type = string
    flag = h"""

    def __init__(
        self, name: str, resource_type: ResourceType, flag: ResourceFlag
    ) -> None:
        self.name = name
        self.type = resource_type
        self.flag = "".join(sorted(flag))
        # remove irrelevant m flag
        self.__flag_simplified = self.flag.replace("m", "")
        self.read_only = False

    @property
    def is_consumable(self) -> bool:
        return self.__flag_simplified in ["fh", "hn", "q", "hnq"]

    @property
    def is_host(self) -> bool:
        return "h" in self.flag

    def __repr__(self) -> str:
        return "ResourceDef(name={}, type={}, flag={})".format(
            self.name, self.type.name, self.flag
        )


class ResourceState:
    def __init__(
        self,
        resources_available: Dict[str, Any],
        resources_assigned: Dict[str, Any],
        shared_resources: Dict[str, List[SharedResource]],
    ) -> None:
        self.resources_available = resources_available
        self.resources_assigned = resources_assigned
        self.shared_resources = shared_resources


def parse_resource_definitions(expr: str) -> Dict[str, PBSProResourceDefinition]:
    return {}
