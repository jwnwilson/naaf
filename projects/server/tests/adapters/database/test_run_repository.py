from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent
from domain.runs.run import Run


def _uow(session_factory):
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})


def test_run_round_trips(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        r = uow.runs.create(
            Run(owner_id="", work_item_id="w1", project_id="p1", autonomy_level="gated_all")
        )
        got = uow.runs.read(r.id)
    assert got.work_item_id == "w1"
    assert got.owner_id == "u1"  # stamped
    assert got.status.value == "queued"


def test_run_event_seq_is_monotonic_per_run(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        e1 = uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        e2 = uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        e3 = uow.run_events.create(RunEvent(owner_id="", run_id="r2", type=EventType.LOG))
    assert (e1.seq, e2.seq) == (1, 2)
    assert e3.seq == 1  # per-run counter resets
