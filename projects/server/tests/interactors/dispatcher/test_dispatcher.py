from adapters.database.uow import SqlUnitOfWork
from adapters.dispatcher.cursor_store import SqlSubscriberCursorStore
from domain.runs.events import EventType, RunEvent
from interactors.dispatcher.dispatcher import dispatch_events
from interactors.dispatcher.subscriber import CursorState


class RecordingSub:
    name = "recorder"

    def __init__(self):
        self.seen = []

    def interested_in(self, event):
        return event.type is EventType.RUN_FINISHED

    def handle(self, event, session):
        self.seen.append(event.global_seq)


class PoisonSub:
    name = "poison"

    def __init__(self):
        self.calls = 0

    def interested_in(self, event):
        return True

    def handle(self, event, session):
        self.calls += 1
        raise ValueError("boom")


class WriteAndFailSub:
    """Writes a side-effect cursor row then raises — exercises partial-write rollback."""

    name = "write_and_fail"

    def __init__(self):
        self.calls = 0

    def interested_in(self, event):
        return True

    def handle(self, event, session):
        self.calls += 1
        # Write a detectable side-effect using the same session.
        SqlSubscriberCursorStore(session).save(
            "sideeffect", CursorState(last_global_seq=999)
        )
        raise ValueError("write then fail")


def _seed_events(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.RUN_FINISHED))


def test_dispatch_advances_cursor_and_filters(session_factory):
    _seed_events(session_factory)
    rec = RecordingSub()
    handled = dispatch_events(session_factory, [rec])
    assert rec.seen == [2]  # only the RUN_FINISHED event (global_seq 2)
    assert handled == 2  # both events consumed (cursor advanced past both)
    # re-run: nothing new
    assert dispatch_events(session_factory, [rec]) == 0
    assert rec.seen == [2]


def test_failing_subscriber_is_isolated_and_dead_letters(session_factory):
    _seed_events(session_factory)
    rec, poison = RecordingSub(), PoisonSub()
    # poison keeps failing; run dispatch enough times to exceed the retry cap
    for _ in range(5):
        dispatch_events(session_factory, [rec, poison])
    assert rec.seen == [2]  # recorder unaffected by poison's failures
    assert poison.calls >= 3  # retried up to the cap, then dead-lettered + advanced


def test_partial_write_rolled_back_on_handle_failure(session_factory):
    # Arrange: seed two events; subscriber writes a side-effect row then raises.
    _seed_events(session_factory)
    sub = WriteAndFailSub()

    # Act: first dispatch — handle raises, retry pending (retries < MAX).
    dispatch_events(session_factory, [sub])

    # Assert via a fresh session so we read committed DB state.
    session = session_factory()
    try:
        store = SqlSubscriberCursorStore(session)

        # (a) The "sideeffect" cursor row must NOT have been persisted (rolled back).
        sideeffect = store.get("sideeffect")
        assert sideeffect.last_global_seq == 0, (
            "partial write should have been rolled back; sideeffect cursor must not exist"
        )

        # (b) The subscriber's own cursor must NOT have advanced (retry still pending).
        own = store.get(sub.name)
        assert own.last_global_seq == 0, "cursor must not advance on a failed handle"
        assert own.retries == 1, "retry counter must be incremented"
    finally:
        session.close()
