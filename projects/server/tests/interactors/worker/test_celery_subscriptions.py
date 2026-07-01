"""Tests for the Task 6 composition root: SUBSCRIPTIONS registry, run_subscription,
and the Celery beat rewire (dispatch-subscriptions replaces drain-bus/dispatch-events).

All DB-touching tests use SQLite in-memory via the session_factory fixture.
No Celery broker required.
"""

from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.runs.events import EventType, RunEvent
from domain.runs.run import Run
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_subscriptions_names():
    from interactors.worker.registry import SUBSCRIPTIONS
    names = {s.name for s in SUBSCRIPTIONS}
    assert names == {"agent-bus", "notifications"}


# ---------------------------------------------------------------------------
# Celery beat schedule
# ---------------------------------------------------------------------------

def test_beat_has_dispatch_subscriptions():
    from interactors.worker.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule
    assert "dispatch-subscriptions" in schedule
    entry = schedule["dispatch-subscriptions"]
    assert entry["task"] == "naaf.dispatch_subscriptions"
    assert entry["schedule"] == 1.0


def test_beat_has_no_drain_bus():
    from interactors.worker.celery_app import celery_app
    assert "drain-bus" not in celery_app.conf.beat_schedule


def test_beat_has_no_dispatch_events():
    from interactors.worker.celery_app import celery_app
    assert "dispatch-events" not in celery_app.conf.beat_schedule


# ---------------------------------------------------------------------------
# run_subscription — notifications parity with old dispatch_events
# ---------------------------------------------------------------------------

def _seed_run_events(session_factory) -> str:
    """Create a project/work-item/run and insert GATE_REQUESTED + RUN_FINISHED events.

    Returns the run_id so the caller can read back notifications.
    """
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(
            Project(owner_id="", name="notif-test-project")
        )
        wi = uow.work_items.create(
            WorkItem(
                owner_id="",
                project_id=project.id,
                kind=WorkItemKind.TASK,
                title="notif-task",
                status=WorkItemStatus.TODO,
            )
        )
        run = uow.runs.create(
            Run(
                owner_id="",
                work_item_id=wi.id,
                project_id=project.id,
                autonomy_level="gated_all",
            )
        )
        uow.run_events.create(
            RunEvent(
                owner_id="",
                run_id=run.id,
                type=EventType.GATE_REQUESTED,
                payload={"kind": "plan"},
            )
        )
        uow.run_events.create(
            RunEvent(
                owner_id="",
                run_id=run.id,
                type=EventType.RUN_FINISHED,
                payload={"status": "succeeded"},
            )
        )
    return run.id


def test_run_subscription_notifications_creates_notifications_for_gate_and_finish(
    session_factory,
):
    """run_subscription('notifications', …) must create one notification per
    GATE_REQUESTED / RUN_FINISHED event — behaviour parity with old dispatch_events."""
    # Arrange
    run_id = _seed_run_events(session_factory)
    runtime = FakeAgentRuntime()

    # Act
    from interactors.worker.subscription_runner import run_subscription
    processed = run_subscription("notifications", session_factory, runtime)

    # Assert — both events handled
    assert processed == 2

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        notifs = uow.notifications.read_multi(
            filters={"run_id": run_id}, page_size=10
        ).results

    assert len(notifs) == 2
    types = {n.type.value for n in notifs}
    assert "gate_pending" in types
    assert "run_succeeded" in types


def test_run_subscription_notifications_is_idempotent(session_factory):
    """Calling run_subscription('notifications', …) twice must not create duplicate
    notifications (idempotency via source_seq guard in NotificationSubscriber)."""
    # Arrange
    _seed_run_events(session_factory)
    runtime = FakeAgentRuntime()

    from interactors.worker.subscription_runner import run_subscription
    run_subscription("notifications", session_factory, runtime)

    # Act — second call
    processed_second = run_subscription("notifications", session_factory, runtime)

    # Assert — cursor already advanced, nothing left to process
    assert processed_second == 0
