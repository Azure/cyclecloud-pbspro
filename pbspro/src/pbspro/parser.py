import io
import os
import typing
from typing import Any, Dict, List, Optional, Set

from hpc.autoscale import hpclogging as logging
from hpc.autoscale.node import constraints as conslib

from pbspro.util import filter_host_resources, filter_non_host_resources

if typing.TYPE_CHECKING:
    from pbspro.pbsqueue import StateCountType  # noqa: F401
    from pbspro.pbsqueue import PBSProLimit
    from pbspro.resource import (  # noqa: F401
        PBSProResourceDefinition,
        ResourceState,
    )


class PBSProParser:
    def __init__(
        self, resource_definitions: Dict[str, "PBSProResourceDefinition"]
    ) -> None:
        self.__resource_definitions = resource_definitions

    @property
    def resource_definitions(self) -> Dict[str, "PBSProResourceDefinition"]:
        return self.__resource_definitions

    def convert_resource_list(self, raw_dict: Dict[str, Any],) -> Dict[str, Any]:
        """
        secondary parsing of Resource_List dictionary. Mostly this will convert
        resources to their appropriate type, as per PBSProResourceDefinition.parse
        """
        ret: Dict[str, Any] = {}

        if "select" in raw_dict:
            ret["select"] = self.parse_select(str(raw_dict["select"]))

        if "schedselect" in raw_dict:
            ret["schedselect"] = self.parse_select(str(raw_dict["schedselect"]))

        if "place" in raw_dict:
            ret["place"] = self.parse_place(raw_dict["place"])

        for key, value in raw_dict.items():
            if key in ret:
                # already handled
                continue

            if isinstance(value, str) and key in self.resource_definitions:
                value = self.resource_definitions[key].type.parse(value)

            ret[key] = value

        return ret

    def parse_range_size(self, expr: str) -> int:
        """
        parses something like 1-100 as 100
        or 1-100:2 as 50 etcz
        We don't care (nor for efficiency, do we want to) to generate
        all possible numbers in the range, just the size.
        """
        if "," in expr:
            return sum([self.parse_range_size(sub_expr) for sub_expr in expr.split(",")])
        step = 1
        if ":" in expr:
            expr, step_expr = expr.split(":")
            step = int(step_expr)

        if "-" not in expr:
            return 1

        start, stop = [int(x) for x in expr.split("-")]
        total_range = stop - start + 1
        if total_range % step == 0:
            return total_range // step
        return total_range // step + 1

    def parse_select(self, select_expression: str) -> List[Dict[str, Any]]:
        # Need to detect when slot_type is specified with `-l select=1:slot_type`
        assert isinstance(select_expression, str)
        chunks: List[Dict[str, Any]] = []

        for chunk_expr in select_expression.split("+"):
            chunk = {}
            # give a default of 1 in case the user assumes 1 with their select
            # i.e. -l select=1:mem=16gb == -l select=mem=16gb
            # if they picked a number it will be overridden below
            chunk["select"] = "1"
            chunk["schedselect"] = "1"
            for expr in chunk_expr.split(":"):
                value: Any

                if "=" not in expr:
                    key, value = "select", int(expr)
                else:
                    key, value = expr.split("=", 1)
                    if key in self.resource_definitions:
                        value = self.resource_definitions[key].type.parse(value)
                    else:
                        logging.warning(
                            "Unknown resource %s: treating as a string.", key
                        )
                    chunk[key] = value
            chunks.append(chunk)

        return chunks

    def parse_place(self, place: str) -> Dict[str, str]:
        """
        arrangement is one of free | pack | scatter | vscatter
        sharing is one of excl | shared | exclhost
        grouping can have only one instance of group=resource
        """
        placement = {"arrangement": "free"}

        if not place:
            return placement

        toks = place.split(":")

        for tok in toks:
            if tok in ["free", "pack", "scatter", "vscatter"]:
                placement["arrangement"] = tok
            elif tok in ["excl", "shared", "exclhost"]:
                placement["sharing"] = tok
            elif tok.startswith("group="):
                placement["grouping"] = tok

        return placement

    def parse_resource_state(
        self,
        odict: Dict[str, Any],
        parent_shared_resources: Optional[Dict[str, "PBSProResourceDefinition"]] = None,
    ) -> "ResourceState":
        source = "{}[{}]".format(odict["obj_type"], odict["name"])

        parent_shared_resources = parent_shared_resources or {}
        non_host_resources = filter_non_host_resources(self.resource_definitions)

        res_avail = self.parse_resources_available(odict)
        res_assigned = self.parse_resources_assigned(odict)

        shared_resources: Dict[str, List[conslib.SharedResource]] = {}

        # load this up with the scheduler shared resources, because
        # from a job pov - it only exists in one queue, so it does not
        # care if the shared constraints are from the queue or are global
        for res_name, shared_res in parent_shared_resources.items():
            if not isinstance(shared_res, list):
                shared_resources[res_name] = [shared_res]
            else:
                shared_resources[res_name] = shared_res + []

        for res_name, initial_value in res_avail.items():
            if res_name not in non_host_resources:
                continue

            resource = non_host_resources[res_name]

            if resource.is_consumable:
                assigned_value = res_assigned.get(res_name) or 0
                res_def = self.resource_definitions.get(res_name)
                if not res_def:
                    logging.error(
                        f"Unknown resource {res_name}. Will not be used for autoscale"
                    )
                    continue
                initial_value = res_def.type.parse(initial_value)
                # type checking gets confused here, but by the time we are doing the `-`
                # they will definitely be numeric
                assigned_value = res_def.type.parse(assigned_value)  # type: ignore
                current_value = initial_value - assigned_value  # type: ignore

                if res_name not in shared_resources:
                    shared_resources[res_name] = []

                queue_shared_resource = conslib.SharedConsumableResource(
                    res_name, source, initial_value, current_value
                )
                shared_resources[res_name].append(queue_shared_resource)
            else:
                # queue level overrides scheduler level, so just pop one if it exists
                shared_resources.pop(res_name, [])
                queue_shared_resource = conslib.SharedNonConsumableResource(
                    res_name, source, initial_value
                )
                shared_resources[res_name] = [queue_shared_resource]

        from pbspro.resource import ResourceState

        return ResourceState(res_avail, res_assigned, shared_resources)

    def parse_state_counts(self, expr: str) -> Dict["StateCountType", int]:
        # avoid circular imports, as parser is a singleton used in multiple places
        from pbspro.pbsqueue import StateCounts

        ret: Dict["StateCountType", int] = {}
        kv_toks = expr.split()
        for kv_tok in kv_toks:
            key, value = kv_tok.split(":", 1)
            assert key in StateCounts
            # I asserted it is the proper literal already
            ret[key] = int(value)  # type: ignore
        return ret

    def parse_prefix_from_dict(
        self,
        prefix: str,
        qconfig: Dict[str, Any],
        filter_is_host: Optional[bool] = None,
    ) -> Dict[str, str]:
        ret = {}
        resource_definitions = self.resource_definitions
        if filter_is_host is not None:
            if filter_is_host:
                resource_definitions = filter_host_resources(resource_definitions)
            else:
                resource_definitions = filter_non_host_resources(resource_definitions)

        for key, value in qconfig.items():
            if key.startswith(prefix + "."):
                resource_name = key[len(prefix + ".") :]
                res_def = self.resource_definitions.get(resource_name)
                if res_def:
                    value = res_def.type.parse(value)
                ret[resource_name] = value

        return ret

    def parse_default_chunk(
        self, nconfig: Dict[str, Any], filter_is_host: Optional[bool] = None
    ) -> Dict[str, str]:
        return self.parse_prefix_from_dict("default_chunk", nconfig, filter_is_host)

    def parse_resources_default(
        self, nconfig: Dict[str, Any], filter_is_host: Optional[bool] = None
    ) -> Dict[str, str]:
        return self.parse_prefix_from_dict("resources_default", nconfig, filter_is_host)

    def parse_resources_available(
        self, nconfig: Dict[str, Any], filter_is_host: Optional[bool] = None
    ) -> Dict[str, str]:
        ret = self.parse_prefix_from_dict(
            "resources_available", nconfig, filter_is_host
        )
        if not os.path.exists("/opt/cycle/pbspro/server_dyn_res/"):
            return ret
        for fil_name in os.listdir("/opt/cycle/pbspro/server_dyn_res/"):
            res_name = fil_name
            path = os.path.join("/opt/cycle/pbspro/server_dyn_res", fil_name)
            with open(path) as fr:
                ret[res_name] = fr.read().strip()
        return ret

    def parse_resources_assigned(
        self, nconfig: Dict[str, Any], filter_is_host: Optional[bool] = None
    ) -> Dict[str, str]:
        return self.parse_prefix_from_dict(
            "resources_assigned", nconfig, filter_is_host
        )

    def parse_key_value(self, raw_output: str) -> List[Dict[str, str]]:
        if raw_output.lower().startswith("no active"):
            # e.g. No Active Nodes, nothing done.
            return []

        ret = []
        current_record: Dict[str, str] = {}

        line_continued: str = ""
        for n, line in enumerate(raw_output.splitlines()):
            line = line.strip()
            if line.startswith("#"):
                continue

            if line.endswith(","):
                line_continued = line_continued + line
                continue
            else:
                line = line_continued + line
                line_continued = ""

            if not line:
                if current_record:
                    ret.append(current_record)
                    current_record = {}
                continue

            if not current_record:
                try:
                    obj_type, obj_name = line.split()
                except ValueError:
                    obj_name = line
                    obj_type = "unknown"

                current_record["obj_type"] = obj_type
                current_record["name"] = obj_name
            else:
                assert (
                    "=" in line
                ), "{} has no = in it. Line {} of the following:\n{}".format(
                    line, n + 1, raw_output
                )

                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                current_record[key] = value

        if current_record:
            ret.append(current_record)

        return ret

    def parse_limit_expression(self, expr: str) -> "PBSProLimit":
        # avoid circular import
        from pbspro.pbsqueue import PBSProLimit

        ret = PBSProLimit()
        expr = expr.replace('"', "")

        toks = [t.strip() for t in expr.split(",")]
        for tok in toks:
            if not tok:
                continue

            if tok.isnumeric():
                # easy case max_run = 20 is equivalent to
                # max_run = [o:PBS_ALL=20]
                ret.overall["PBS_ALL"] = int(tok)
                continue

            tok = tok.replace("[", "").replace("]", "")
            key, value = tok.split("=", 1)
            key, value = key.strip(), value.strip()
            parsed_value = int(value)

            scope, name = key.split(":", 1)
            if scope == "o":
                ret.overall[name] = parsed_value
            elif scope == "u":
                ret.user[name] = parsed_value
            elif scope == "g":
                ret.group[name] = parsed_value
            elif scope == "p":
                ret.project[name] = parsed_value
            else:
                raise RuntimeError(
                    "Unknown scope '{}' while parsing limit '{}'".format(scope, tok)
                )

        return ret

    def parse_resources_from_sched_priv(self, path: str) -> Set[str]:

        with io.open(path, "r", encoding="utf-8") as fr:
            for line in fr.readlines():
                line = line.strip()
                if not line.startswith("resources:"):
                    continue
                line = line[len("resources:") :].strip().replace('"', "")
                return set([t.strip() for t in line.split(",")])
        raise RuntimeError(
            "Could not find line beginning with 'resources:' in file {}".format(path)
        )


_PARSER = None


def get_pbspro_parser() -> PBSProParser:
    global _PARSER
    if _PARSER is None:
        # avoid circular import
        from pbspro.pbscmd import PBSCMD
        from pbspro.resource import read_resource_definitions

        # chicken / egg issue: we want the  resource definitions
        # as a member of the parser, but we need the parser to parse
        # the definitions...
        # So create temp parser with no resource definitions
        _PARSER = PBSProParser({})
        pbscmd = PBSCMD(_PARSER)
        logging.warning(
            "Using uninitialized PBSProParser: please call"
            + " set_pbspro_parser before calling get_pbspro_parser"
        )
        resource_definitions = read_resource_definitions(pbscmd, {})
        _PARSER = PBSProParser(resource_definitions)
    return _PARSER


def set_pbspro_parser(parser: PBSProParser) -> None:
    global _PARSER
    # no explict type check in case someone wants to duck type
    _PARSER = parser
