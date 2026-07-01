"""Tests for the old celery_app.drain() helper and drain-bus beat entry.

Task 6 removed drain_bus / drain from celery_app.py; the equivalent
integration coverage moved to test_celery_subscriptions.py.
The drain-function tests below are marked xfail and will be deleted in Task 7
when processor.py itself is removed.
"""
import pytest

# ---------------------------------------------------------------------------
# Beat schedule — updated to new entry (Task 6)
# ---------------------------------------------------------------------------

def test_celery_app_import_is_db_and_broker_free():
    """Importing celery_app must not open a DB connection or require a broker."""
    from interactors.worker.celery_app import celery_app
    assert celery_app.main == "naaf"
    assert celery_app.conf.worker_concurrency == 1


def test_celery_beat_schedule_contains_dispatch_subscriptions():
    """Beat schedule must include dispatch-subscriptions (replaces drain-bus)."""
    from interactors.worker.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule
    assert "dispatch-subscriptions" in schedule
    entry = schedule["dispatch-subscriptions"]
    assert entry["task"] == "naaf.dispatch_subscriptions"
    assert entry["schedule"] == 1.0


# ---------------------------------------------------------------------------
# drain() helper — removed in Task 6; will be cleaned up in Task 7
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason="drain() helper removed from celery_app in Task 6; "
           "equivalent coverage in test_celery_subscriptions.py; "
           "remaining dead code cleaned up in Task 7",
    raises=(ImportError, AttributeError),
    strict=True,
)
def test_drain_processes_start_message_and_returns_positive_count(session_factory):
    from adapters.agent.runtime.fake import FakeAgentRuntime
    from adapters.bus.factory import build_message_bus
    from adapters.database.uow import SqlUnitOfWork
    from domain.project import Project
    from domain.runs.messages import AgentMessage, MessageType, recipient_key
    from domain.runs.run import Run, RunStatus
    from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus
    from interactors.worker.celery_app import drain  # removed in Task 6

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="", name="drain-test-project"))
        work_item = uow.work_items.create(
            WorkItem(owner_id="", project_id=project.id, kind=WorkItemKind.TASK,
                     title="drain-task", status=WorkItemStatus.IN_PROGRESS)
        )
        run = uow.runs.create(
            Run(owner_id="", work_item_id=work_item.id, project_id=project.id,
                autonomy_level="full_auto")
        )
    run_id = run.id
    session = session_factory()
    bus = build_message_bus(session)
    bus.publish(AgentMessage(owner_id="u1", run_id=run_id,
                             recipient=recipient_key(run_id, "lead"),
                             role="lead", type=MessageType.START))
    session.commit()
    session.close()

    count = drain(session_factory, FakeAgentRuntime())
    assert count >= 1
    uow2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow2.transaction():
        r = uow2.runs.read(run_id)
    assert r.status == RunStatus.SUCCEEDED


@pytest.mark.xfail(
    reason="drain() helper removed from celery_app in Task 6; cleaned up in Task 7",
    raises=(ImportError, AttributeError),
    strict=True,
)
def test_drain_on_empty_queue_returns_zero(session_factory):
    from adapters.agent.runtime.fake import FakeAgentRuntime
    from interactors.worker.celery_app import drain  # removed in Task 6
    count = drain(session_factory, FakeAgentRuntime())
    assert count == 0


@pytest.mark.xfail(
    reason="drain() helper removed from celery_app in Task 6; cleaned up in Task 7",
    raises=(ImportError, AttributeError),
    strict=True,
)
def test_drain_second_call_on_drained_queue_returns_zero(session_factory):
    from adapters.agent.runtime.fake import FakeAgentRuntime
    from interactors.worker.celery_app import drain  # removed in Task 6
    count = drain(session_factory, FakeAgentRuntime())
    assert count == 0


@pytest.mark.xfail(
    reason="drain-bus beat entry removed in Task 6; cleaned up in Task 7",
    raises=AssertionError,
    strict=True,
)
def test_celery_beat_schedule_contains_drain_bus_task():
    from interactors.worker.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule
    assert "drain-bus" in schedule
    assert schedule["drain-bus"]["task"] == "naaf.drain_bus"
    assert schedule["drain-bus"]["schedule"] == 1.0
