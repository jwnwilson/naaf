"""Unit tests for domain/messaging/subscribers/notifications.py.

These tests are PURE — no database, no session, no adapter imports.
The fake ctx exposes a notifications repo double.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from domain.messaging.subscribers.notifications import NotificationSubscriber
from domain.notifications.notification import NotificationType
from domain.runs.events import EventType, RunEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(**kwargs) -> RunEvent:
    defaults = dict(owner_id="owner-1", run_id="run-1", type=EventType.RUN_STARTED)
    defaults.update(kwargs)
    return RunEvent(**defaults)


def _make_ctx(existing_results=None):
    """Build a fake HandlerContext with a notifications repo double."""
    repo = MagicMock()
    page = MagicMock()
    page.results = existing_results or []
    repo.read_multi.return_value = page
    ctx = SimpleNamespace(notifications=repo)
    return ctx, repo


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_name_is_notifications():
    assert NotificationSubscriber().name == "notifications"


# ---------------------------------------------------------------------------
# interested_in
# ---------------------------------------------------------------------------

def test_interested_in_run_finished():
    sub = NotificationSubscriber()
    assert sub.interested_in(_event(type=EventType.RUN_FINISHED)) is True


def test_not_interested_in_run_started():
    sub = NotificationSubscriber()
    assert sub.interested_in(_event(type=EventType.RUN_STARTED)) is False


def test_interested_in_gate_requested():
    sub = NotificationSubscriber()
    assert sub.interested_in(_event(type=EventType.GATE_REQUESTED)) is True


# ---------------------------------------------------------------------------
# handle — gate_requested creates a GATE_PENDING notification via ctx.notifications
# ---------------------------------------------------------------------------

def test_handle_gate_requested_creates_gate_pending_notification():
    # Arrange
    sub = NotificationSubscriber()
    event = _event(type=EventType.GATE_REQUESTED, payload={"kind": "plan"}, global_seq=7)
    ctx, repo = _make_ctx()

    # Act
    sub.handle(event, ctx)

    # Assert — idempotency pre-check used the right filter
    repo.read_multi.assert_called_once_with(filters={"source_seq": 7}, page_size=1)

    # Assert — create was called with a GATE_PENDING notification
    repo.create.assert_called_once()
    notif = repo.create.call_args[0][0]
    assert notif.type == NotificationType.GATE_PENDING
    assert notif.run_id == "run-1"
    assert notif.source_seq == 7
    assert notif.owner_id == "owner-1"


def test_handle_skips_create_when_notification_already_exists():
    # Arrange
    sub = NotificationSubscriber()
    event = _event(type=EventType.GATE_REQUESTED, payload={"kind": "plan"}, global_seq=5)
    existing = MagicMock()
    ctx, repo = _make_ctx(existing_results=[existing])

    # Act
    sub.handle(event, ctx)

    # Assert — idempotency short-circuits before create
    repo.create.assert_not_called()


def test_handle_run_finished_creates_run_succeeded_notification():
    # Arrange
    sub = NotificationSubscriber()
    event = _event(type=EventType.RUN_FINISHED, payload={"status": "succeeded"}, global_seq=9)
    ctx, repo = _make_ctx()

    # Act
    sub.handle(event, ctx)

    # Assert
    notif = repo.create.call_args[0][0]
    assert notif.type == NotificationType.RUN_SUCCEEDED
    assert notif.source_seq == 9
    assert notif.owner_id == "owner-1"


def test_handle_run_finished_creates_run_failed_notification():
    # Arrange
    sub = NotificationSubscriber()
    event = _event(type=EventType.RUN_FINISHED, payload={"status": "failed"}, global_seq=10)
    ctx, repo = _make_ctx()

    # Act
    sub.handle(event, ctx)

    # Assert
    notif = repo.create.call_args[0][0]
    assert notif.type == NotificationType.RUN_FAILED
    assert notif.source_seq == 10
    assert notif.owner_id == "owner-1"


def test_handle_run_finished_creates_run_cancelled_notification():
    # Arrange
    sub = NotificationSubscriber()
    event = _event(type=EventType.RUN_FINISHED, payload={"status": "cancelled"}, global_seq=11)
    ctx, repo = _make_ctx()

    # Act
    sub.handle(event, ctx)

    # Assert
    notif = repo.create.call_args[0][0]
    assert notif.type == NotificationType.RUN_CANCELLED
    assert notif.source_seq == 11
    assert notif.owner_id == "owner-1"
