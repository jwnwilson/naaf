from adapters.database.event_log_source import EventLogSource
from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent


def _sf_uow(session_factory):
    return SqlUnitOfWork(session_factory)   # system uow (no owner filter)


def test_event_log_source_fetch_advance(session_factory):
    owned = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with owned.transaction():
        owned.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.RUN_FINISHED))
    src = EventLogSource("notifications")
    uow = _sf_uow(session_factory)
    with uow.transaction():
        item = src.fetch_next(uow)
        assert item is not None and item.owner_id == "u1" and item.position == 1
        src.advance(item, uow)
    uow2 = _sf_uow(session_factory)
    with uow2.transaction():
        assert src.fetch_next(uow2) is None   # cursor advanced past the only event
