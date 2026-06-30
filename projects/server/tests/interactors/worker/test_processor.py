from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.sql import SqlMessageBus
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus
from interactors.worker.processor import process_next


def test_process_next_returns_false_when_empty(session_factory):
    assert process_next(session_factory, SqlMessageBus(), FakeAgentRuntime()) is False


def test_process_next_handles_a_start_message(session_factory):
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
    bus = SqlMessageBus()
    session = session_factory()
    bus.publish(
        AgentMessage(
            owner_id="u1",
            run_id=run.id,
            recipient=recipient_key(run.id, "lead"),
            role="lead",
            type=MessageType.START,
        ),
        session,
    )
    session.commit()
    session.close()

    # Act
    result = process_next(session_factory, bus, FakeAgentRuntime())

    # Assert
    assert result is True
    uow2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow2.transaction():
        events = uow2.run_events.read_multi(filters={"run_id": run.id}).results
    assert any(e.type.value == "run_started" for e in events)
