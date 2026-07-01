from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent
from interactors.dispatcher.dispatcher import dispatch_events


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


def _seed_events(session_factory, n):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.RUN_FINISHED))


def test_dispatch_advances_cursor_and_filters(session_factory):
    _seed_events(session_factory, 2)
    rec = RecordingSub()
    handled = dispatch_events(session_factory, [rec])
    assert rec.seen == [2]  # only the RUN_FINISHED event (global_seq 2)
    assert handled == 2  # both events consumed (cursor advanced past both)
    # re-run: nothing new
    assert dispatch_events(session_factory, [rec]) == 0
    assert rec.seen == [2]


def test_failing_subscriber_is_isolated_and_dead_letters(session_factory):
    _seed_events(session_factory, 2)
    rec, poison = RecordingSub(), PoisonSub()
    # poison keeps failing; run dispatch enough times to exceed the retry cap
    for _ in range(5):
        dispatch_events(session_factory, [rec, poison])
    assert rec.seen == [2]  # recorder unaffected by poison's failures
    assert poison.calls >= 3  # retried up to the cap, then dead-lettered + advanced
