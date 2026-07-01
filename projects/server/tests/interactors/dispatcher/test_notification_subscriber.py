from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent
from interactors.dispatcher.dispatcher import dispatch_events
from interactors.dispatcher.subscribers.notifications import NotificationSubscriber


def _seed(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.RUN_STARTED))
        uow.run_events.create(
            RunEvent(
                owner_id="",
                run_id="r1",
                type=EventType.GATE_REQUESTED,
                payload={"kind": "plan"},
            )
        )
        uow.run_events.create(
            RunEvent(
                owner_id="",
                run_id="r1",
                type=EventType.RUN_FINISHED,
                payload={"status": "succeeded"},
            )
        )


def _notifs(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        return uow.notifications.read_multi(page_size=0).results


def test_notifications_created_for_gate_and_finish_idempotently(session_factory):
    # Arrange
    _seed(session_factory)
    sub = NotificationSubscriber()

    # Act
    dispatch_events(session_factory, [sub])

    # Assert: only gate_pending + run_succeeded created; run_started ignored
    n = _notifs(session_factory)
    types = sorted(x.type.value for x in n)
    assert types == ["gate_pending", "run_succeeded"]
    assert all(x.owner_id == "u1" for x in n)

    # Idempotency: re-running dispatch over the same events produces no duplicates
    dispatch_events(session_factory, [sub])
    assert len(_notifs(session_factory)) == 2
