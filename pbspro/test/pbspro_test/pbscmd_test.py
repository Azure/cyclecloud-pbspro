import pytest

from pbspro.parser import PBSProParser


@pytest.mark.skip
def test_missing_binaries() -> None:
    assert False, "check response from which('qstat') etc"


def test_qmgr_parsed(parser: PBSProParser) -> None:
    example = """Queue workq
    queue_type = Execution
    total_jobs = 0
    state_count = Transit:0 Queued:0 Held:0 Waiting:0 Running:0 Exiting:0 Begun:0
    resources_default.place = scatter
    enabled = True
    started = True

Queue htcq
    queue_type = Execution
    total_jobs = 0
    state_count = Transit:0 Queued:0 Held:0 Waiting:0 Running:0 Exiting:0 Begun:0
    resources_default.place = pack
    enabled = True
    started = True"""
    expected = [
        {
            "obj_type": "Queue",
            "name": "workq",
            "queue_type": "Execution",
            "total_jobs": "0",
            "state_count": "Transit:0 Queued:0 Held:0 Waiting:0 Running:0 Exiting:0 Begun:0",
            "resources_default.place": "scatter",
            "enabled": "True",
            "started": "True",
        },
        {
            "obj_type": "Queue",
            "name": "htcq",
            "queue_type": "Execution",
            "total_jobs": "0",
            "state_count": "Transit:0 Queued:0 Held:0 Waiting:0 Running:0 Exiting:0 Begun:0",
            "resources_default.place": "pack",
            "enabled": "True",
            "started": "True",
        },
    ]
    actual = parser.parse_key_value(example)

    # instead of 'obj_type obj_name' as the first line
    # (i.e. 'Queue htcq') it is simply 'obj_name'. We expect
    # obj_type to be "unknown" in this case
    pbsnodes_example = """
ip-0A010008
     Mom = ip-0a010008.ryan.com
     Port = 15002
     pbs_version = 20.0.1
     ntype = PBS"""

    expected = [
        {
            "obj_type": "unknown",
            "name": "ip-0A010008",
            "Mom": "ip-0a010008.ryan.com",
            "Port": "15002",
            "pbs_version": "20.0.1",
            "ntype": "PBS",
        }
    ]

    actual = parser.parse_key_value(pbsnodes_example)

    assert actual == expected
