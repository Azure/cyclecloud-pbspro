from pbspro.parser import PBSProParser


def test_parse_state_counts(parser: PBSProParser) -> None:
    expr = "Transit:1 Queued:2 Held:3 Waiting:4 Running:5 Exiting:6 Begun:7"
    expected = {
        "Transit": 1,
        "Queued": 2,
        "Held": 3,
        "Waiting": 4,
        "Running": 5,
        "Exiting": 6,
        "Begun": 7,
    }
    actual = parser.parse_state_counts(expr)
    assert expected == actual


def test_parse_defaults(parser: PBSProParser) -> None:
    qdict = {
        "obj_type": "Queue",
        "name": "workq",
        "queue_type": "Execution",
        "total_jobs": "0",
        "state_count": "Transit:0 Queued:0 Held:0 Waiting:0 Running:0 Exiting:0 Begun:0",
        "resources_default.place": "scatter",
        "resources_default.abc": "false",
        "default_chunk.abc": "true",
        "resources_available.qres": 100,
        "enabled": "True",
        "started": "True",
    }

    expected = {"place": "scatter", "abc": False}

    actual = parser.parse_resources_default(qdict)
    assert actual == expected
    actual = parser.parse_default_chunk(qdict)
    assert {"abc": True} == actual
    assert {"qres": 100} == parser.parse_resources_available(qdict)


def test_parse_range_size(parser: PBSProParser) -> None:
    assert 1 == parser.parse_range_size("1")
    assert 1 == parser.parse_range_size("4")
    assert 10 == parser.parse_range_size("1-10")
    assert 5 == parser.parse_range_size("1-10:2")
    assert 5 == parser.parse_range_size("1-9:2")
    assert 4 == parser.parse_range_size("1-10:3")
    assert 3 == parser.parse_range_size("1-9:3")
    assert 3 == parser.parse_range_size("101-109:3")

    assert 5 == parser.parse_range_size("1-2,5-7")
    assert 10 == parser.parse_range_size("1-2,5-7,11-20:2")
