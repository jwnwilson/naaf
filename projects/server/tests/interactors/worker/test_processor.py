"""Bus-draining integration tests (formerly driven via process_next; now via run_subscription).

Drives the agent-bus subscription via run_subscription("agent-bus", …) — the
unified engine entry point that replaced the old process_next helper.

Parity assertions are preserved:
- empty bus → 0 returned
- START message → processed, run_started event written
- poison (bogus role) → dead-lettered, not re-delivered, run marked failed
"""
from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.sql import SqlMessageBus
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run, RunStatus
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus
from interactors.worker.subscription_runner import run_subscription


def test_run_subscription_returns_zero_when_empty(session_factory):
    assert run_subscription("agent-bus", session_factory, FakeAgentRuntime()) == 0


def test_run_subscription_handles_a_start_message(session_factory):
    # Arrange — seed project, work item, and run for owner "u1"
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="", name="p1"))
        work_item = uow.work_items.create(
            WorkItem(
                owner_id="",
                project_id=project.id,
                kind=WorkItemKind.TASK,
                title="task",
                status=WorkItemStatus.IN_PROGRESS,
            )
        )
        run = uow.runs.create(
            Run(
                owner_id="",
                work_item_id=work_item.id,
                project_id=project.id,
                autonomy_level="full_auto",
            )
        )

    # Publish a START message targeting the lead
    session = session_factory()
    SqlMessageBus(session).publish(
        AgentMessage(
            owner_id="u1",
            run_id=run.id,
            recipient=recipient_key(run.id, "lead"),
            role="lead",
            type=MessageType.START,
        ),
    )
    session.commit()
    session.close()

    # Act
    result = run_subscription("agent-bus", session_factory, FakeAgentRuntime())

    # Assert — at least one item processed (the START triggers further bus messages)
    assert result >= 1
    uow2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow2.transaction():
        events = uow2.run_events.read_multi(filters={"run_id": run.id}).results
    assert any(e.type.value == "run_started" for e in events)


def test_run_subscription_isolates_poison_message_without_crashing(session_factory):
    """A message with an unknown role causes dispatch to raise ValueError.

    run_subscription must:
    - NOT propagate the exception (returns >= 1 instead of raising)
    - Dead-letter the message (a second call returns 0 — not re-delivered)
    - Mark the run as failed
    """
    # Arrange — seed a run so the poison message references a real run
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="", name="p_poison"))
        work_item = uow.work_items.create(
            WorkItem(owner_id="", project_id=project.id, kind=WorkItemKind.TASK,
                     title="poison_task", status=WorkItemStatus.IN_PROGRESS)
        )
        run = uow.runs.create(
            Run(owner_id="", work_item_id=work_item.id, project_id=project.id,
                autonomy_level="full_auto")
        )

    # Publish a message with a bogus role — dispatch raises ValueError("unknown role")
    session = session_factory()
    SqlMessageBus(session).publish(
        AgentMessage(
            owner_id="u1",
            run_id=run.id,
            recipient="u1:" + run.id + ":bogus",
            role="bogus",
            type=MessageType.START,
        ),
    )
    session.commit()
    session.close()

    # Act — must NOT raise
    result = run_subscription("agent-bus", session_factory, FakeAgentRuntime())
    assert result >= 1, "run_subscription should return >= 1 (work consumed) even on dispatch error"

    # Assert — message is dead-lettered (not re-delivered)
    assert run_subscription("agent-bus", session_factory, FakeAgentRuntime()) == 0, \
        "poison message must not be re-delivered after dead-lettering"

    # Assert — run is marked failed
    uow2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow2.transaction():
        failed_run = uow2.runs.read(run.id)
    assert failed_run.status == RunStatus.FAILED, \
        f"run should be failed after poison dispatch, got {failed_run.status}"
