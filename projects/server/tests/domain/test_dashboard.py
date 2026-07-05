from datetime import UTC, date, datetime

from domain.dashboard import build_token_series, to_activity_event
from domain.runs.events import EventType, RunEvent
from domain.runs.run import Stage


def _evt(type_: EventType, *, tokens: int | None = None, when: datetime | None = None,
         role: str | None = None, stage: Stage | None = None, id_: str = "e") -> RunEvent:
    payload = {"tokens": tokens} if tokens is not None else {}
    return RunEvent(owner_id="o", run_id="r", type=type_, payload=payload,
                    role=role, stage=stage, created_at=when)


TODAY = date(2026, 7, 5)


def test_token_series_has_seven_zero_filled_days_oldest_first():
    series = build_token_series([], TODAY)
    assert len(series) == 7
    assert series[0].day == "2026-06-29"
    assert series[-1].day == "2026-07-05"
    assert all(p.tokens == 0 for p in series)


def test_token_series_sums_payload_tokens_into_the_right_day():
    d = datetime(2026, 7, 4, 10, tzinfo=UTC)
    events = [
        _evt(EventType.STAGE_PASSED, tokens=300, when=d),
        _evt(EventType.STAGE_FAILED, tokens=200, when=d),
        _evt(EventType.STAGE_PASSED, tokens=1000, when=datetime(2026, 7, 5, 9, tzinfo=UTC)),
    ]
    series = {p.day: p.tokens for p in build_token_series(events, TODAY)}
    assert series["2026-07-04"] == 500
    assert series["2026-07-05"] == 1000


def test_token_series_ignores_events_outside_window_and_without_tokens():
    events = [
        _evt(EventType.STAGE_PASSED, tokens=999, when=datetime(2026, 6, 1, tzinfo=UTC)),  # too old
        _evt(EventType.STAGE_STARTED, when=datetime(2026, 7, 5, tzinfo=UTC)),  # no tokens
    ]
    assert all(p.tokens == 0 for p in build_token_series(events, TODAY))


def test_token_series_ignores_event_with_no_created_at():
    events = [_evt(EventType.STAGE_PASSED, tokens=500, when=None)]
    assert all(p.tokens == 0 for p in build_token_series(events, TODAY))


def test_activity_mapping_per_type():
    when = datetime(2026, 7, 5, tzinfo=UTC)
    cases = {
        EventType.RUN_STARTED: ("status_change", "Run started"),
        EventType.STAGE_STARTED: ("status_change", "engineer started implement"),
        EventType.STAGE_PASSED: ("agent_write", "engineer finished implement"),
        EventType.STAGE_FAILED: ("run_failed", "implement failed"),
        EventType.GATE_REQUESTED: ("status_change", "Gate requested (implement)"),
        EventType.GATE_RESOLVED: ("status_change", "Gate resolved (implement)"),
        EventType.RUN_FINISHED: ("run_complete", "Run finished"),
    }
    for et, (want_type, want_desc) in cases.items():
        item = to_activity_event(_evt(et, when=when, role="engineer", stage=Stage.IMPLEMENT))
        assert item is not None
        assert item.type == want_type
        assert item.description == want_desc
        assert item.agent_id == "engineer"
        assert item.work_item_id is None


def test_activity_log_event_is_skipped():
    assert to_activity_event(_evt(EventType.LOG, when=datetime(2026, 7, 5, tzinfo=UTC))) is None


def test_activity_role_and_stage_fallbacks():
    item = to_activity_event(_evt(EventType.STAGE_STARTED,
                                  when=datetime(2026, 7, 5, tzinfo=UTC)))
    assert item.description == "agent started "  # role→"agent", stage→""
