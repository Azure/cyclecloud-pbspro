import pytest
from hpc.autoscale.job.schedulernode import SchedulerNode
from hpc.autoscale.node.constraints import SharedConsumableResource

from pbspro.parser import PBSProParser
from pbspro.pbsqueue import PBSProLimit, PBSProQueue
from pbspro.resource import LongType, PBSProResourceDefinition, ResourceState


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

    test_queue = PBSProQueue(
        name="testq",
        queue_type="execution",
        total_jobs=0,
        state_count={},
        resources_default={},
        default_chunk={},
        node_group_enable=True,
        node_group_key="group_id",
        resource_state=ResourceState(
            resources_available={},
            resources_assigned={},
            shared_resources={
                "qres": [
                    SharedConsumableResource(
                        resource_name="qres",
                        source="queue",
                        current_value=4,
                        initial_value=4,
                    )
                ]
            },
        ),
        resource_definitions={
            "qres": PBSProResourceDefinition("qres", LongType(), flag="q")
        },
        enabled=True,
        started=True,
    )
    non_host_cons = test_queue.get_non_host_constraints({"qres": 1, "other": 2}, 1)
    assert len(non_host_cons) == 1
    assert len(non_host_cons[0].shared_resources) == 1

    assert non_host_cons[0].shared_resources[0].resource_name == "qres"
    assert non_host_cons[0].shared_resources[0].initial_value == 4
    assert non_host_cons[0].shared_resources[0].current_value == 4

    assert test_queue.resource_state.shared_resources["qres"][0].current_value == 4
    snode = SchedulerNode("localhost", {})
    assert snode.decrement(non_host_cons)
    assert test_queue.resource_state.shared_resources["qres"][0].current_value == 3


def test_shared_resource_decremented_once_across_nodes() -> None:
    # A queue-level (flag=q) consumable is consumed once for the whole job,
    # not once per node. A multi-node job (nodect > 1) reuses the same
    # constraint instance for each node it spans, so the shared value must
    # only be decremented a single time - and the request must stay integral.
    test_queue = PBSProQueue(
        name="testq",
        queue_type="execution",
        total_jobs=0,
        state_count={},
        resources_default={},
        default_chunk={},
        node_group_enable=True,
        node_group_key="group_id",
        resource_state=ResourceState(
            resources_available={},
            resources_assigned={},
            shared_resources={
                "qres": [
                    SharedConsumableResource(
                        resource_name="qres",
                        source="queue",
                        current_value=10,
                        initial_value=10,
                    )
                ]
            },
        ),
        resource_definitions={
            "qres": PBSProResourceDefinition("qres", LongType(), flag="q")
        },
        enabled=True,
        started=True,
    )

    # Job requests qres=1 and spans 3 nodes.
    non_host_cons = test_queue.get_non_host_constraints({"qres": 1}, 3)
    assert len(non_host_cons) == 1

    qres = test_queue.resource_state.shared_resources["qres"][0]

    # Simulate the autoscaler decrementing once per node the job spans.
    for i in range(3):
        snode = SchedulerNode("localhost-{}".format(i), {})
        assert snode.decrement(non_host_cons)

    # Exactly one unit consumed total (not 3), and the value remains an int.
    assert qres.current_value == 9, "Expected 9, got {!r}".format(qres.current_value)
    assert isinstance(
        qres.current_value, int
    ), "Expected int, got {}".format(type(qres.current_value).__name__)


@pytest.mark.skip
def test_disabled_queues() -> None:
    assert False
