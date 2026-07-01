"""Tests for interactors.worker.celery_app.drain().

All tests run against SQLite in-memory — no Celery broker or Redis required.
"""
from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.factory import build_message_bus
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run, RunStatus
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus
from interactors.worker.celery_app import celery_app, drain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed(session_factory):
    """Create a project + work item + run owned by 'u1', return the run id."""
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="", name="drain-test-project"))
        work_item = uow.work_items.create(
            WorkItem(
                owner_id="",
                project_id=project.id,
                kind=WorkItemKind.TASK,
                title="drain-task",
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
    return run.id


def _publish_start(session_factory, run_id: str) -> None:
    """Publish a START message for the lead agent via the bus factory."""
    session = session_factory()
    bus = build_message_bus(session)
    bus.publish(
        AgentMessage(
            owner_id="u1",
            run_id=run_id,
            recipient=recipient_key(run_id, "lead"),
            role="lead",
            type=MessageType.START,
        )
    )
    session.commit()
    session.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_drain_processes_start_message_and_returns_positive_count(session_factory):
    """Arrange: seed run + publish START. Act: drain. Assert: >=1 processed, run progressed."""
    # Arrange
    run_id = _seed(session_factory)
    _publish_start(session_factory, run_id)

    # Act
    count = drain(session_factory, FakeAgentRuntime())

    # Assert — at least the START message was handled (full_auto will drain all the way)
    assert count >= 1

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.read(run_id)
        events = uow.run_events.read_multi(filters={"run_id": run_id}).results

    assert run.status == RunStatus.SUCCEEDED
    assert any(e.type.value == "run_started" for e in events)


def test_drain_on_empty_queue_returns_zero(session_factory):
    """With no messages in the bus, drain should return 0 immediately."""
    count = drain(session_factory, FakeAgentRuntime())
    assert count == 0


def test_drain_second_call_on_drained_queue_returns_zero(session_factory):
    """After a full drain, calling drain again returns 0 (idempotent)."""
    # Arrange
    run_id = _seed(session_factory)
    _publish_start(session_factory, run_id)

    # Act — first drain processes all messages
    first = drain(session_factory, FakeAgentRuntime())
    assert first >= 1

    # Act — second drain finds nothing
    second = drain(session_factory, FakeAgentRuntime())
    assert second == 0


def test_celery_app_import_is_db_and_broker_free():
    """Importing celery_app must not open a DB connection or require a broker.

    The module-level Settings() call is fine; only _deps() (called inside the
    task) touches heavy resources, and it is decorated with @lru_cache so it
    is deferred until first invocation.
    """
    # celery_app is already imported at the top of this module — if the import
    # triggered DB/broker connections it would have failed during collection.
    assert celery_app.main == "naaf"
    assert celery_app.conf.worker_concurrency == 1


def test_celery_beat_schedule_contains_drain_bus_task():
    """Beat schedule must include the 'drain-bus' entry pointing at naaf.drain_bus."""
    schedule = celery_app.conf.beat_schedule
    assert "drain-bus" in schedule
    entry = schedule["drain-bus"]
    assert entry["task"] == "naaf.drain_bus"
    assert entry["schedule"] == 1.0
