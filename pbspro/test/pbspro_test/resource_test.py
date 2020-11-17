from hpc.autoscale.hpctypes import Size as HPCSize

from pbspro.resource import (
    BooleanType,
    DurationType,
    FloatType,
    LongType,
    PBSProResourceDefinition,
    ResourceParsingError,
    SizeType,
    StringType,
)


def test_parse_boolean() -> None:

    for x in ["TRUE", "True", "true", "T", "t", "Y", "y", "1"]:
        assert BooleanType().parse(x)

    for x in ["FALSE", "False", "false", "F", "f", "N", "n", "0"]:
        assert not BooleanType().parse(x)

    try:
        BooleanType().parse("tRue")
        assert False
    except ResourceParsingError:
        pass


def test_parse_duration() -> None:

    assert 1 == DurationType().parse("1")
    assert 1 == DurationType().parse("1.0")
    assert 1 == DurationType().parse("1.49")
    assert 2 == DurationType().parse("1.5")

    assert 61 == DurationType().parse("1:1")
    assert 62 == DurationType().parse("1:1.5")
    assert 3661 == DurationType().parse("1:1:1")
    assert 3662 == DurationType().parse("1:1:1.5")

    try:
        DurationType().parse("1:1:1:1.5")
        assert False
    except ResourceParsingError:
        pass

    try:
        DurationType().parse(".5")
        assert False
    except ResourceParsingError:
        pass


def test_parse_float() -> None:
    assert abs(1.1 - FloatType().parse("1.1")) < 1e20
    assert abs(-1.1 - FloatType().parse("-1.1")) < 1e20


def test_parse_long() -> None:
    assert 1 == LongType().parse("1")
    assert -1 == LongType().parse("-1")
    assert 1 == LongType().parse("+1")


def test_parse_size() -> None:
    # ensure our custom sizes work (*w word based sizes are supported)
    # where one word is 64bits, so 1kw == 8k
    assert HPCSize.value_of("1") == SizeType().parse("1")
    assert HPCSize.value_of("1b") == SizeType().parse("1b")
    assert HPCSize.value_of("8b") == SizeType().parse("1w")
    assert HPCSize.value_of("8k") == SizeType().parse("1kw")
    assert HPCSize.value_of("8m") == SizeType().parse("1mw")
    assert HPCSize.value_of("8g") == SizeType().parse("1gw")
    assert HPCSize.value_of("8t") == SizeType().parse("1tw")
    assert HPCSize.value_of("8p") == SizeType().parse("1pw")


def test_pbspro_resource() -> None:
    ncpus = PBSProResourceDefinition("ncpus", LongType(), "nh")
    ccnodeid = PBSProResourceDefinition("ccnodeid", StringType(), "h")
    qres = PBSProResourceDefinition("qres", LongType(), "q")
    sres = PBSProResourceDefinition("sres", LongType(), "")

    assert ncpus.is_consumable
    assert ncpus.is_host

    assert not ccnodeid.is_consumable
    assert ccnodeid.is_host

    assert qres.is_consumable
    assert not qres.is_host

    assert not sres.is_consumable
    assert not sres.is_host
