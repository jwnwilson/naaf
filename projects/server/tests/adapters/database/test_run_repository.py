from datetime import datetime

from adapters.database.uow import SqlUnitOfWork
from domain.base import utcnow
from domain.runs.events import EventType, RunEvent
from domain.runs.run import Run, Stage, StageState, StageStatus


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


def test_run_stages_with_datetime_round_trips(session_factory):
    # Arrange
    started = utcnow()
    stage_state = StageState(
        stage=Stage.PLAN,
        status=StageStatus.RUNNING,
        role="lead",
        started_at=started,
    )
    uow = _uow(session_factory)

    # Act
    with uow.transaction():
        r = uow.runs.create(
            Run(
                owner_id="",
                work_item_id="w1",
                project_id="p1",
                autonomy_level="gated_all",
                stages=[stage_state],
            )
        )
        got = uow.runs.read(r.id)

    # Assert
    assert len(got.stages) == 1
    s = got.stages[0]
    assert isinstance(s, StageState)
    assert s.stage is Stage.PLAN
    assert isinstance(s.started_at, datetime)


def test_run_event_seq_is_monotonic_per_run(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        e1 = uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        e2 = uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        e3 = uow.run_events.create(RunEvent(owner_id="", run_id="r2", type=EventType.LOG))
    assert (e1.seq, e2.seq) == (1, 2)
    assert e3.seq == 1  # per-run counter resets
