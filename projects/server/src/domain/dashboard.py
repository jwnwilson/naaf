from collections.abc import Callable
from datetime import date, datetime, timedelta

from pydantic import BaseModel

from domain.runs.events import EventType, RunEvent


class TokenPoint(BaseModel):
    day: str  # YYYY-MM-DD
    tokens: int


class ActivityItem(BaseModel):
    id: str
    type: str
    description: str
    agent_id: str | None = None
    work_item_id: str | None = None
    created_at: datetime


def build_token_series(
    events: list[RunEvent], today: date, days: int = 7
) -> list[TokenPoint]:
    """Bucket per-stage token deltas (RunEvent.payload['tokens']) into the last
    `days` calendar days ending at `today`, zero-filled, oldest->newest."""
    day_list = [today - timedelta(days=days - 1 - i) for i in range(days)]
    totals: dict[date, int] = {d: 0 for d in day_list}
    for e in events:
        if e.created_at is None:
            continue
        d = e.created_at.date()
        if d in totals:
            totals[d] += int(e.payload.get("tokens", 0) or 0)
    return [TokenPoint(day=d.isoformat(), tokens=totals[d]) for d in day_list]


def _role(e: RunEvent) -> str:
    return e.role or "agent"


def _stage(e: RunEvent) -> str:
    return e.stage.value if e.stage else ""


# EventType -> (activity type, description builder). Missing types (LOG) are skipped.
_ACTIVITY_MAP: dict[EventType, tuple[str, Callable[[RunEvent], str]]] = {
    EventType.RUN_STARTED: ("status_change", lambda e: "Run started"),
    EventType.STAGE_STARTED: ("status_change", lambda e: f"{_role(e)} started {_stage(e)}"),
    EventType.STAGE_PASSED: ("agent_write", lambda e: f"{_role(e)} finished {_stage(e)}"),
    EventType.STAGE_FAILED: ("run_failed", lambda e: f"{_stage(e)} failed"),
    EventType.GATE_REQUESTED: ("status_change", lambda e: f"Gate requested ({_stage(e)})"),
    EventType.GATE_RESOLVED: ("status_change", lambda e: f"Gate resolved ({_stage(e)})"),
    EventType.RUN_FINISHED: ("run_complete", lambda e: "Run finished"),
}


def to_activity_event(event: RunEvent) -> ActivityItem | None:
    """Map a RunEvent to an activity row, or None for events that shouldn't show
    (log noise)."""
    entry = _ACTIVITY_MAP.get(event.type)
    if entry is None:
        return None
    type_, describe = entry
    return ActivityItem(
        id=event.id,
        type=type_,
        description=describe(event),
        agent_id=event.role,
        work_item_id=None,
        created_at=event.created_at,
    )
