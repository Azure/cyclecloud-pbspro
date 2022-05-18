import os
from typing import Dict, Tuple

from hpc.autoscale import hpclogging as logging
from hpc.autoscale.hpctypes import Hostname
from hpc.autoscale.util import partition_single

from pbspro.constants import ServerStates
from pbspro.parser import get_pbspro_parser
from pbspro.pbscmd import PBSCMD
from pbspro.resource import BooleanType, PBSProResourceDefinition, ResourceState


class PBSProScheduler:
    def __init__(
        self, sched_dict: Dict[str, str], resource_state: ResourceState,
    ) -> None:
        btype = BooleanType()
        self.do_not_span_psets = btype.parse(
            sched_dict.get("do_not_span_psets", "false")
        )
        self.scheduling = btype.parse(sched_dict["scheduling"])
        self.only_explicit_psets = btype.parse(
            sched_dict.get("only_explicit_psets", "false")
        )
        self.node_group_enable = btype.parse(
            sched_dict.get("node_group_enable", "false")
        )
        self.node_group_key = sched_dict.get("node_group_key")

        self.sched_log = sched_dict["sched_log"]
        self.sched_priv = sched_dict["sched_priv"]
        priv_config_path = os.path.join(self.sched_priv, "sched_config")
        self.resources_for_scheduling = get_pbspro_parser().parse_resources_from_sched_priv(
            priv_config_path
        )
        self.state = sched_dict["state"]
        self.hostname = sched_dict["sched_host"].split(".")[0]
        self.resource_state = resource_state

        try:
            self.pbs_version: Tuple = tuple(
                [int(x) for x in sched_dict["pbs_version"].split(".")]
            )
        except ValueError:
            self.pbs_version = tuple(sched_dict["pbs_version"].split("."))
        self.sched_dict = sched_dict

        if not self.only_explicit_psets:
            logging.error(
                "only_explicit_psets must be set to true. You can change this by running:"
                + ' qmgr -c "set sched default only_explicit_psets = true'
            )

    @property
    def is_active(self) -> bool:
        return self.state.lower() in [
            ServerStates.Idle.lower(),
            ServerStates.Hot_Start.lower(),
            ServerStates.Scheduling.lower(),
        ]

    @property
    def is_default(self) -> bool:
        return self.sched_dict["name"] == "default"

    def __repr__(self) -> str:
        return "Scheduler(hostname={}, state={})".format(self.hostname, self.state,)


def read_schedulers(
    pbscmd: PBSCMD, resource_definitions: Dict[str, PBSProResourceDefinition]
) -> Dict[Hostname, PBSProScheduler]:
    parser = get_pbspro_parser()
    sched_dicts = pbscmd.qmgr_parsed("list", "sched")
    server_dicts = pbscmd.qmgr_parsed("list", "server")

    server_dicts_by_host = partition_single(server_dicts, lambda s: s["server_host"])

    ret: Dict[str, PBSProScheduler] = {}

    for sched_dict in sched_dicts:
        hostname = sched_dict["sched_host"]
        server_dict = server_dicts_by_host[hostname]

        for key, value in server_dict.items():
            if key not in sched_dict:
                sched_dict[key] = value

        # this is a scheduler, so it has no parent shared resources
        resource_state = parser.parse_resource_state(
            sched_dict, parent_shared_resources=None
        )
        scheduler = PBSProScheduler(sched_dict, resource_state)
        ret[scheduler.hostname] = scheduler

    return ret
