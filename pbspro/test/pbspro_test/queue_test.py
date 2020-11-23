from pbspro.parser import PBSProParser
from pbspro.queue import PBSProLimit


def test_parse_limit_expression(parser: PBSProParser) -> None:
    lim = PBSProLimit()

    p = parser.parse_limit_expression

    assert lim == p("")
    lim.overall["PBS_ALL"] = 20
    assert lim == p("20")
    assert lim == p("[o:PBS_ALL=20]")

    lim.user["ryan"] = 15
    assert lim == p("[o:PBS_ALL=20], [u:ryan=15]")

    lim.group["devs"] = 10
    assert lim == p("[o:PBS_ALL=20], [u:ryan=15], [g:devs=10]")

    lim.project["rnd"] = 5
    assert lim == p("[o:PBS_ALL=20], [u:ryan=15], [g:devs=10], [p:rnd=5]")

    lim = p(
        "[o:PBS_ALL=20], [u:ryan=15], [u:PBS_GENERIC=14], [g:devs=10], [g:PBS_GENERIC=9], [p:rnd=5], [p:PBS_GENERIC=4]"
    )
    # no user, group or project, so use the overall one.
    assert 20 == lim.get_limit()
    # individual limit for ryan
    assert 15 == lim.get_limit(user="ryan")
    assert 14 == lim.get_limit(user="brian")

    assert 10 == lim.get_limit(groups=["devs"])
    assert 10 == lim.get_limit(user="ryan", groups=["devs"])
    assert 10 == lim.get_limit(user="brian", groups=["devs"])
    assert 5 == lim.get_limit(project="rnd", groups=["devs"])
    assert 4 == lim.get_limit(project="act", groups=["devs"])
    assert 4 == lim.get_limit(user="ryan", project="act", groups=["devs"])
    assert 4 == lim.get_limit(user="ryan", project="act", groups=["devs", "act"])
    assert 15 == lim.get_limit(user="ryan", groups=["devs", "act"])

    assert 9 == lim.get_limit(groups=["act"])
    assert 9 == lim.get_limit(groups=["act"])

    assert 19 == lim.get_limit(groups=["devs", "act"])

    assert 5 == lim.get_limit(project="rnd")
    assert 4 == lim.get_limit(project="legacy")


def test_non_schedulable_shared_resources() -> None:
    # what if say, qres is created but is not used for scheduling
    # what happens if it hits the limit any ways?
    assert False, "implement"
