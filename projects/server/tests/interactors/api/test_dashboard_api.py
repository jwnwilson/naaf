from datetime import UTC, datetime, timedelta

from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent
from domain.runs.run import Stage


def _seed_event(session_factory, owner: str, *, type_: EventType, tokens=None,
                when=None, role=None, stage=None):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction() as u:
        u.run_events.create(RunEvent(
            owner_id="", run_id="run-x", type=type_,
            payload=({"tokens": tokens} if tokens is not None else {}),
            role=role, stage=stage, created_at=when,
        ))


def test_token_usage_returns_seven_points_summed_per_day(client, session_factory):
    now = datetime.now(UTC)
    _seed_event(session_factory, "dev-user", type_=EventType.STAGE_PASSED, tokens=400, when=now)
    _seed_event(session_factory, "dev-user", type_=EventType.STAGE_FAILED, tokens=100, when=now)
    body = client.get("/dashboard/token-usage").json()
    assert body["success"] is True
    pts = body["data"]
    assert len(pts) == 7
    today = now.date().isoformat()
    assert next(p for p in pts if p["day"] == today)["tokens"] == 500


def test_token_usage_is_owner_scoped(client, client_other_owner, session_factory):
    _seed_event(session_factory, "dev-user", type_=EventType.STAGE_PASSED, tokens=999,
                when=datetime.now(UTC))
    other = client_other_owner.get("/dashboard/token-usage").json()["data"]
    assert all(p["tokens"] == 0 for p in other)


def test_activity_maps_events_newest_first_and_excludes_log(client, session_factory):
    base = datetime.now(UTC)
    _seed_event(
        session_factory, "dev-user",
        type_=EventType.RUN_STARTED, when=base - timedelta(minutes=3),
    )
    _seed_event(
        session_factory, "dev-user",
        type_=EventType.LOG, when=base - timedelta(minutes=2),
    )
    _seed_event(
        session_factory, "dev-user",
        type_=EventType.STAGE_PASSED, when=base - timedelta(minutes=1),
        role="engineer", stage=Stage.IMPLEMENT,
    )
    rows = client.get("/activity").json()["data"]
    # newest first, log dropped
    assert [r["type"] for r in rows] == ["agent_write", "status_change"]
    assert rows[0]["description"] == "engineer finished implement"


def test_activity_is_owner_scoped(client, client_other_owner, session_factory):
    _seed_event(session_factory, "dev-user", type_=EventType.RUN_STARTED, when=datetime.now(UTC))
    assert client_other_owner.get("/activity").json()["data"] == []
