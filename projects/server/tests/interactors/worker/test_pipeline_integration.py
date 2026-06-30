"""Full fake-pipeline integration tests.

Drives the entire run pipeline through process_next with the real (SQLite) bus
and FakeAgentRuntime, proving three scenarios:
1. full_auto run completes to succeeded with work_item done.
2. gated_all run pauses at the plan gate; approving it advances to merge gate.
3. FakeAgentRuntime(fail_verify_times=1) retries IMPLEMENT then succeeds.
"""
from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.sql import SqlMessageBus
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run
from domain.work_item import WorkItem, WorkItemKind
from interactors.worker.processor import process_next


def _seed(session_factory, autonomy):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="", name="P", autonomy_level=autonomy))
        wi = uow.work_items.create(WorkItem(owner_id="", project_id=p.id, kind=WorkItemKind.TASK,
                                            title="T", status="todo"))
        run = uow.runs.create(
            Run(owner_id="", work_item_id=wi.id, project_id=p.id, autonomy_level=autonomy)
        )
    return wi.id, run.id


def _drain(session_factory, bus, runtime):
    while process_next(session_factory, bus, runtime):
        pass


def _start(bus, session_factory, run_id):
    s = session_factory()
    bus.publish(
        AgentMessage(owner_id="u1", run_id=run_id, recipient=recipient_key(run_id, "lead"),
                     role="lead", type=MessageType.START),
        s,
    )
    s.commit()


def _read_run(session_factory, run_id):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.read(run_id)
        events = uow.run_events.read_multi(filters={"run_id": run_id}, page_size=0).results
        return run, events


def test_full_auto_run_succeeds_without_gates(session_factory):
    bus, rt = SqlMessageBus(), FakeAgentRuntime()
    wi_id, run_id = _seed(session_factory, "full_auto")
    _start(bus, session_factory, run_id)
    _drain(session_factory, bus, rt)
    run, events = _read_run(session_factory, run_id)
    assert run.status.value == "succeeded"
    assert {e.type.value for e in events} >= {"run_started", "stage_passed", "run_finished"}
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        assert uow.work_items.read(wi_id).status.value == "done"


def test_gated_all_pauses_at_plan_gate_then_resumes(session_factory):
    bus, rt = SqlMessageBus(), FakeAgentRuntime()
    _, run_id = _seed(session_factory, "gated_all")
    _start(bus, session_factory, run_id)
    _drain(session_factory, bus, rt)
    run, _ = _read_run(session_factory, run_id)
    assert run.status.value == "awaiting_gate" and run.pending_gate.kind.value == "plan"
    # approve the plan gate
    s = session_factory()
    bus.publish(
        AgentMessage(owner_id="u1", run_id=run_id, recipient=recipient_key(run_id, "lead"),
                     role="lead", type=MessageType.GATE_RESOLVED,
                     payload={"decision": "approve"}),
        s,
    )
    s.commit()
    _drain(session_factory, bus, rt)
    run, _ = _read_run(session_factory, run_id)
    # next pause is the merge gate
    assert run.status.value == "awaiting_gate" and run.pending_gate.kind.value == "merge"


def test_verify_retry_then_success(session_factory):
    bus, rt = SqlMessageBus(), FakeAgentRuntime(fail_verify_times=1)
    _, run_id = _seed(session_factory, "full_auto")
    _start(bus, session_factory, run_id)
    _drain(session_factory, bus, rt)
    run, events = _read_run(session_factory, run_id)
    assert run.status.value == "succeeded"
    assert run.verify_attempts == 1
    implement_starts = sum(
        1 for e in events
        if e.stage and e.stage.value == "implement" and e.type.value == "stage_started"
    )
    assert implement_starts >= 2
