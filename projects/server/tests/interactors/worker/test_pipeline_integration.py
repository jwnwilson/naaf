"""Full fake-pipeline integration tests.

Drives the entire run pipeline through run_subscription("agent-bus", …) with
the real (SQLite) bus and FakeAgentRuntime, proving three scenarios:
1. full_auto run completes to succeeded with work_item done.
2. gated_all run pauses at the plan gate; approving it advances to merge gate.
3. FakeAgentRuntime(fail_verify_times=1) retries IMPLEMENT then succeeds.
"""
from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.factory import build_message_bus
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run
from domain.work_item import WorkItem, WorkItemKind
from interactors.worker.subscription_runner import run_subscription


def _seed(session_factory, autonomy):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    # owner_id is overridden to "u1" by required_filters at repo-create time
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="", name="P", autonomy_level=autonomy))
        wi = uow.work_items.create(WorkItem(owner_id="", project_id=p.id, kind=WorkItemKind.TASK,
                                            title="T", status="todo"))
        run = uow.runs.create(
            Run(owner_id="", work_item_id=wi.id, project_id=p.id, autonomy_level=autonomy)
        )
    return wi.id, run.id


def _drain(session_factory, runtime):
    while run_subscription("agent-bus", session_factory, runtime):
        pass


def _start(session_factory, run_id):
    s = session_factory()
    build_message_bus(s).publish(
        AgentMessage(owner_id="u1", run_id=run_id, recipient=recipient_key(run_id, "lead"),
                     role="lead", type=MessageType.START),
    )
    s.commit()


def _read_run(session_factory, run_id):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.read(run_id)
        events = uow.run_events.read_multi(filters={"run_id": run_id}, page_size=0).results
        return run, events


def test_full_auto_run_succeeds_without_gates(session_factory):
    rt = FakeAgentRuntime()
    wi_id, run_id = _seed(session_factory, "full_auto")
    _start(session_factory, run_id)
    _drain(session_factory, rt)
    run, events = _read_run(session_factory, run_id)
    assert run.status.value == "succeeded"
    assert {e.type.value for e in events} >= {"run_started", "stage_passed", "run_finished"}
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        assert uow.work_items.read(wi_id).status.value == "done"
    # Fix 3: stages timeline must be populated with plan/implement/verify entries
    assert run.stages, "run.stages must be non-empty after a completed run"
    by_stage = {s.stage.value: s for s in run.stages}
    expected_stages = (("plan", "lead"), ("implement", "engineer"), ("verify", "qa"))
    for stage_name, expected_role in expected_stages:
        assert stage_name in by_stage, f"stage {stage_name!r} missing from run.stages"
        entry = by_stage[stage_name]
        assert entry.status.value == "passed", (
            f"stage {stage_name} expected passed, got {entry.status}"
        )
        assert entry.role == expected_role, (
            f"stage {stage_name} expected role {expected_role!r}, got {entry.role!r}"
        )


def test_gated_all_pauses_at_plan_gate_then_resumes(session_factory):
    rt = FakeAgentRuntime()
    _, run_id = _seed(session_factory, "gated_all")
    _start(session_factory, run_id)
    _drain(session_factory, rt)
    run, _ = _read_run(session_factory, run_id)
    assert run.status.value == "awaiting_gate" and run.pending_gate.kind.value == "plan"
    # approve the plan gate
    s = session_factory()
    build_message_bus(s).publish(
        AgentMessage(owner_id="u1", run_id=run_id, recipient=recipient_key(run_id, "lead"),
                     role="lead", type=MessageType.GATE_RESOLVED,
                     payload={"decision": "approve"}),
    )
    s.commit()
    _drain(session_factory, rt)
    run, _ = _read_run(session_factory, run_id)
    # next pause is the merge gate
    assert run.status.value == "awaiting_gate" and run.pending_gate.kind.value == "merge"


def test_duplicate_gate_resolved_is_a_harmless_noop(session_factory):
    """Publishing GATE_RESOLVED twice (double-click) must not crash the worker.

    The first message resolves the plan gate and advances the run; the second
    hits pending_gate=None and is silently dropped. The run ends at the merge gate.
    """
    rt = FakeAgentRuntime()
    _, run_id = _seed(session_factory, "gated_all")
    _start(session_factory, run_id)
    _drain(session_factory, rt)
    run, _ = _read_run(session_factory, run_id)
    assert run.status.value == "awaiting_gate" and run.pending_gate.kind.value == "plan"

    # Publish GATE_RESOLVED/approve TWICE — simulating a double-click
    for _ in range(2):
        s = session_factory()
        build_message_bus(s).publish(
            AgentMessage(owner_id="u1", run_id=run_id, recipient=recipient_key(run_id, "lead"),
                         role="lead", type=MessageType.GATE_RESOLVED,
                         payload={"decision": "approve"}),
        )
        s.commit()

    # Drain — worker must not raise; duplicate is a no-op
    _drain(session_factory, rt)

    run, _ = _read_run(session_factory, run_id)
    # Run advanced past the plan gate and is now paused at the merge gate
    assert run.status.value == "awaiting_gate", f"expected awaiting_gate, got {run.status}"
    assert run.pending_gate.kind.value == "merge"


def test_run_accumulates_token_usage_from_stages(session_factory):
    rt = FakeAgentRuntime()
    _wi_id, run_id = _seed(session_factory, "full_auto")
    _start(session_factory, run_id)
    _drain(session_factory, rt)
    run, events = _read_run(session_factory, run_id)
    passed_tokens = sum(
        e.payload.get("tokens", 0) for e in events if e.type.value == "stage_passed"
    )
    assert run.token_usage > 0
    assert run.token_usage == passed_tokens


def test_token_usage_counts_failed_stage_attempts(session_factory):
    """token_usage must include tokens from failed stage attempts, not just passed ones.

    When VERIFY fails once and is retried, the failed attempt genuinely consumed
    tokens, so token_usage > sum(tokens over stage_passed events). The true
    invariant is: token_usage == sum(tokens over all stage_passed + stage_failed events).
    """
    # Arrange
    rt = FakeAgentRuntime(fail_verify_times=1)
    _wi_id, run_id = _seed(session_factory, "full_auto")

    # Act
    _start(session_factory, run_id)
    _drain(session_factory, rt)
    run, events = _read_run(session_factory, run_id)

    # Assert
    passed_tokens = sum(
        e.payload.get("tokens", 0) for e in events if e.type.value == "stage_passed"
    )
    all_runtime_tokens = sum(
        e.payload.get("tokens", 0)
        for e in events
        if e.type.value in ("stage_passed", "stage_failed")
    )
    assert run.status.value == "succeeded"
    assert run.token_usage == all_runtime_tokens, (
        f"token_usage {run.token_usage} != all_runtime_tokens {all_runtime_tokens}"
    )
    assert run.token_usage > passed_tokens, (
        f"token_usage {run.token_usage} should exceed passed-only tokens {passed_tokens} "
        "because the failed VERIFY attempt also consumed tokens"
    )


def test_verify_retry_then_success(session_factory):
    rt = FakeAgentRuntime(fail_verify_times=1)
    _, run_id = _seed(session_factory, "full_auto")
    _start(session_factory, run_id)
    _drain(session_factory, rt)
    run, events = _read_run(session_factory, run_id)
    assert run.status.value == "succeeded"
    assert run.verify_attempts == 1
    implement_starts = sum(
        1 for e in events
        if e.stage and e.stage.value == "implement" and e.type.value == "stage_started"
    )
    assert implement_starts >= 2
