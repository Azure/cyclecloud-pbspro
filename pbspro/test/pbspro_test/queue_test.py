import pytest
from hpc.autoscale.job.schedulernode import SchedulerNode
from hpc.autoscale.node.constraints import (
    SharedConsumableConstraint,
    SharedConsumableResource,
)

from pbspro.parser import PBSProParser
from pbspro.pbsqueue import PBSProLimit, PBSProQueue, QueueLimitTracker
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
    assert isinstance(qres.current_value, int), "Expected int, got {}".format(
        type(qres.current_value).__name__
    )


@pytest.mark.skip
def test_disabled_queues() -> None:
    assert False


# ---------------------------------------------------------------------------
# Run-limit parsing (parser.parse_queue_limits)
# ---------------------------------------------------------------------------


def test_parse_max_run_res_ncpus_user_generic(parser: PBSProParser) -> None:
    limits = parser.parse_queue_limits({"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"})
    assert len(limits) == 1
    lim = limits[0]
    assert lim.source_attr == "max_run_res.ncpus"
    assert lim.resource == "ncpus"
    assert not lim.is_count
    assert lim.limit.user["PBS_GENERIC"] == 1200


def test_parse_max_run_bare_integer_is_overall(parser: PBSProParser) -> None:
    limits = parser.parse_queue_limits({"max_run": "20"})
    assert len(limits) == 1
    lim = limits[0]
    assert lim.is_count
    assert lim.resource is None
    assert lim.limit.overall["PBS_ALL"] == 20


def test_parse_all_scope_forms_in_one_expression(parser: PBSProParser) -> None:
    limits = parser.parse_queue_limits(
        {
            "max_run": "[o:PBS_ALL=20], [u:ryan=15], [u:PBS_GENERIC=14], [g:devs=10], [p:rnd=5]"
        }
    )
    assert len(limits) == 1
    lim = limits[0].limit
    assert lim.overall["PBS_ALL"] == 20
    assert lim.user["ryan"] == 15
    assert lim.user["PBS_GENERIC"] == 14
    assert lim.group["devs"] == 10
    assert lim.project["rnd"] == 5


def test_parse_legacy_max_user_run_and_max_group_run(parser: PBSProParser) -> None:
    limits = parser.parse_queue_limits({"max_user_run": "14", "max_group_run": "10"})
    by_attr = {lim.source_attr: lim for lim in limits}
    assert all(lim.is_count for lim in limits)
    assert by_attr["max_user_run"].limit.user["PBS_GENERIC"] == 14
    assert by_attr["max_group_run"].limit.group["PBS_GENERIC"] == 10


def test_parse_malformed_limit_is_skipped_and_logged(parser: PBSProParser) -> None:
    # the malformed max_run is skipped without aborting; the valid resource
    # limit on the same queue still parses (R7).
    limits = parser.parse_queue_limits(
        {"max_run": "not-a-limit", "max_run_res.ncpus": "[u:PBS_GENERIC=1200]"}
    )
    assert len(limits) == 1
    assert limits[0].source_attr == "max_run_res.ncpus"


def test_parse_queue_without_limits_yields_no_limits(parser: PBSProParser) -> None:
    limits = parser.parse_queue_limits(
        {"resources_max.ncpus": "44", "enabled": "True", "started": "True"}
    )
    assert limits == []


# ---------------------------------------------------------------------------
# QueueLimitTracker: budget resolution, usage aggregation, constraints
# ---------------------------------------------------------------------------


def _tracker(
    parser: PBSProParser, qconfig: dict, queue_name: str = "long"
) -> QueueLimitTracker:
    return QueueLimitTracker(queue_name, parser.parse_queue_limits(qconfig))


def _pool(constraint: SharedConsumableConstraint) -> SharedConsumableResource:
    return constraint.shared_resources[0]


def test_budget_generic_user_falls_back_when_name_absent(parser: PBSProParser) -> None:
    tracker = _tracker(parser, {"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"})
    cons = tracker.get_constraints("alice", None, None, {"ncpus": 100})
    assert len(cons) == 1
    assert _pool(cons[0]).current_value == 1200


def test_budget_specific_user_overrides_generic(parser: PBSProParser) -> None:
    tracker = _tracker(parser, {"max_run": "[u:ryan=15], [u:PBS_GENERIC=14]"})
    ryan = tracker.get_constraints("ryan", None, None, {})
    brian = tracker.get_constraints("brian", None, None, {})
    assert _pool(ryan[0]).current_value == 15
    assert _pool(brian[0]).current_value == 14


def test_budget_is_min_across_applicable_scopes(parser: PBSProParser) -> None:
    # a job bound by both an overall and a stricter per-user limit draws from
    # both pools, so the effective cap is the smaller of the two.
    tracker = _tracker(parser, {"max_run": "[o:PBS_ALL=10], [u:PBS_GENERIC=5]"})
    cons = tracker.get_constraints("alice", None, None, {})
    values = sorted(_pool(c).current_value for c in cons)
    assert values == [5, 10]


def test_budget_subtracts_running_resource_usage(parser: PBSProParser) -> None:
    tracker = _tracker(parser, {"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"})
    tracker.add_running_usage("alice", None, None, {"ncpus": 800})
    cons = tracker.get_constraints("alice", None, None, {"ncpus": 100})
    assert _pool(cons[0]).current_value == 400


def test_budget_subtracts_running_job_count(parser: PBSProParser) -> None:
    tracker = _tracker(parser, {"max_run": "[u:PBS_GENERIC=5]"})
    tracker.add_running_usage("alice", None, None, {})
    tracker.add_running_usage("alice", None, None, {})
    cons = tracker.get_constraints("alice", None, None, {})
    assert _pool(cons[0]).current_value == 3


def test_budget_floors_at_zero_when_usage_exceeds_limit(parser: PBSProParser) -> None:
    tracker = _tracker(parser, {"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"})
    tracker.add_running_usage("alice", None, None, {"ncpus": 1500})
    cons = tracker.get_constraints("alice", None, None, {"ncpus": 100})
    assert _pool(cons[0]).current_value == 0


def test_usage_sums_resource_across_running_jobs_by_user(
    parser: PBSProParser,
) -> None:
    tracker = _tracker(parser, {"max_run_res.ncpus": "[u:PBS_GENERIC=2000]"})
    tracker.add_running_usage("alice", None, None, {"ncpus": 300})
    tracker.add_running_usage("alice", None, None, {"ncpus": 500})
    tracker.add_running_usage("bob", None, None, {"ncpus": 100})
    alice = tracker.get_constraints("alice", None, None, {"ncpus": 1})
    bob = tracker.get_constraints("bob", None, None, {"ncpus": 1})
    assert _pool(alice[0]).current_value == 2000 - 800
    assert _pool(bob[0]).current_value == 2000 - 100


def test_usage_counts_running_jobs_by_group(parser: PBSProParser) -> None:
    tracker = _tracker(parser, {"max_run": "[g:PBS_GENERIC=10]"})
    tracker.add_running_usage(None, "devs", None, {})
    tracker.add_running_usage(None, "devs", None, {})
    cons = tracker.get_constraints(None, "devs", None, {})
    assert len(cons) == 1
    assert _pool(cons[0]).current_value == 8


def test_constraint_added_for_job_under_active_limit(parser: PBSProParser) -> None:
    tracker = _tracker(parser, {"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"})
    cons = tracker.get_constraints("alice", None, None, {"ncpus": 100})
    assert len(cons) == 1
    assert isinstance(cons[0], SharedConsumableConstraint)
    # a resource limit consumes the job's full request from the pool.
    node = SchedulerNode("tux", {})
    assert cons[0].satisfied_by_node(node)
    assert cons[0].do_decrement(node)
    assert _pool(cons[0]).current_value == 1100


def test_no_constraint_when_scope_has_no_limit(parser: PBSProParser) -> None:
    # only ryan is limited; alice matches no specific nor PBS_GENERIC entry.
    tracker = _tracker(parser, {"max_run_res.ncpus": "[u:ryan=15]"})
    cons = tracker.get_constraints("alice", None, None, {"ncpus": 100})
    assert cons == []


def test_distinct_users_get_distinct_budget_pools(parser: PBSProParser) -> None:
    tracker = _tracker(parser, {"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"})
    alice = tracker.get_constraints("alice", None, None, {"ncpus": 100})
    bob = tracker.get_constraints("bob", None, None, {"ncpus": 100})
    assert _pool(alice[0]) is not _pool(bob[0])

    node = SchedulerNode("tux", {})
    # fully consume alice's budget with fresh (per-job) constraint instances.
    for _ in range(12):
        job_cons = tracker.get_constraints("alice", None, None, {"ncpus": 100})
        assert job_cons[0].do_decrement(node)

    assert _pool(alice[0]).current_value == 0
    # bob's pool is untouched.
    assert _pool(bob[0]).current_value == 1200


def test_indivisible_job_exceeding_budget_is_not_placed(
    parser: PBSProParser,
) -> None:
    tracker = _tracker(parser, {"max_run_res.ncpus": "[u:PBS_GENERIC=1200]"})
    tracker.add_running_usage("alice", None, None, {"ncpus": 800})  # remaining 400
    cons = tracker.get_constraints("alice", None, None, {"ncpus": 500})
    assert len(cons) == 1

    node = SchedulerNode("tux", {})
    # a single job needing 500 against a 400 budget cannot be placed at all...
    assert not cons[0].satisfied_by_node(node)
    assert not cons[0].do_decrement(node)
    # ...and the budget is never driven negative.
    assert _pool(cons[0]).current_value == 400
