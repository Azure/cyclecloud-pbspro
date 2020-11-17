import typing_extensions
from typing import Any, Dict
from abc import abstractmethod
from hpc.autoscale.hpctypes import Size as HPCSize, add_magnitude_conversion


add_magnitude_conversion("w", 8)
add_magnitude_conversion("kw", 8 * 1024)
add_magnitude_conversion("mw", 8 * (1024 ** 2))
add_magnitude_conversion("gw", 8 * (1024 ** 3))
add_magnitude_conversion("tw", 8 * (1024 ** 4))
add_magnitude_conversion("pw", 8 * (1024 ** 5))


# fmt: off
ResourceFlag = typing_extensions.Literal[
    "",    # non-consumable queue or server level
    "fh",  # consumable on the first host
    "h",   # non-consumable host
    "nh",  # consumable host
    "q",   # consumable at queue or server
]
# fmt: on

ResourceTypeNames = typing_extensions.Literal["boolean", "duration"]


class ResourceParsingError(RuntimeError):
    pass


class ResourceType:
    @abstractmethod
    def parse(self, expr: str) -> Any:
        ...


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



class PBSProResource:
    """Resource slot_type
    type = string
    flag = h

Resource group_id
    type = string
    flag = h

Resource ungrouped
    type = string
    flag = h

Resource instance_id
    type = string
    flag = h

Resource machinetype
    type = string
    flag = h

Resource nodearray
    type = string
    flag = h

Resource disk
    type = size
    flag = h

Resource ngpus
    type = size
    flag = h"""

    def __init__(
        self, name: str, resource_type: ResourceType, flag: ResourceFlag
    ) -> None:
        pass


def parse_resource_definitions(expr: str) -> Dict[str, PBSProResource]:
    return {}
