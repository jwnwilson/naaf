# Dashboard TokenChart + ActivityFeed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two remaining mocked dashboard widgets — TokenChart (daily token usage) and ActivityFeed (recent activity) — with real data derived from `RunEvent`s.

**Architecture:** Two pure domain aggregators over the owner's `RunEvent` stream (`build_token_series` buckets per-stage token deltas by day; `to_activity_event` maps events to activity rows). A new `routes/dashboard.py` serves `GET /dashboard/token-usage` and `GET /activity`, owner-scoped, read-only — no new table or migration. The UI just polls the two now-live endpoints; the components are unchanged.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (read-only), pydantic v2; React + Vite + React Query + MSW; pytest + Vitest.

**Reference spec:** `docs/superpowers/specs/2026-07-05-dashboard-token-activity-design.md`

## Global Constraints

- Python ≥ 3.12; `uv`; domain logic pure (no I/O, no adapter imports).
- API envelope `{success, data, error}` via `crud_router.ok`; `Envelope[...]` response_model.
- Owner scoping: both routes read through `get_uow`; the UoW stamps `owner_id` on every query — no cross-owner data.
- Token deltas live in `RunEvent.payload["tokens"]` on `stage_passed`/`stage_failed` events only; other events contribute 0.
- TokenChart window = **7 days**, inclusive, ending at server `today` (`datetime.now(UTC).date()`), zero-filled, oldest→newest. Output shape `[{day: "YYYY-MM-DD", tokens: int}]`.
- ActivityFeed: newest-first, cross-run, owner-scoped; `log` events excluded; capped at **20**. Row type ∈ `agent_write | status_change | run_complete | run_failed` (matches the existing `ActivityEvent` contract).
- Activity mapping (exact): `run_started→status_change "Run started"`, `stage_started→status_change "{role} started {stage}"`, `stage_passed→agent_write "{role} finished {stage}"`, `stage_failed→run_failed "{stage} failed"`, `gate_requested→status_change "Gate requested ({stage})"`, `gate_resolved→status_change "Gate resolved ({stage})"`, `run_finished→run_complete "Run finished"`, `log→None`. `{role}` falls back to `"agent"`, `{stage}` to `""`.
- `work_item_id` on activity rows = `null` (avoid N+1). `agent_id = event.role`.
- Polling: `DASHBOARD_POLL_MS = 10000`, hidden-tab pause (React Query default `refetchIntervalInBackground: false`).
- The TokenChart/ActivityFeed components are NOT modified — contract shapes match the fixtures.
- TDD; failing test first; AAA. `make coverage` (80%) + `make lint`; UI `pnpm test` + `pnpm lint` + `pnpm build` green.
- Commit format `<type>: <description>`. Backend tests from `projects/server`; UI tests from `projects/ui`.

## File Structure

**New — backend**
- `projects/server/src/domain/dashboard.py` — `TokenPoint`, `ActivityItem`, `build_token_series`, `to_activity_event` (pure).
- `projects/server/src/interactors/api/routes/dashboard.py` — the two GET routes.
- Tests: `projects/server/tests/domain/test_dashboard.py`, `projects/server/tests/interactors/api/test_dashboard_api.py`.

**Modified — backend**
- `projects/server/src/interactors/api/contract.py` — `TokenPointOut`, `ActivityEventOut`.
- `projects/server/src/interactors/api/routes/__init__.py` — register `dashboard_router`.

**Modified — UI**
- `projects/ui/src/lib/api/hooks/useDashboard.ts` — `DASHBOARD_POLL_MS` + `refetchInterval` on `useTokenUsage`/`useActivity`.
- `projects/ui/src/lib/api/mocks/handlers.ts` — move `/dashboard/token-usage` + `/activity` to `liveHandlers`.
- `projects/ui/src/lib/api/hooks/useDashboard.test.tsx` (new) — poll + live-shape.
- `docs/project-history.md` — status entry (final task).

---

### Task 1: Domain aggregators — `domain/dashboard.py`

**Files:**
- Create: `projects/server/src/domain/dashboard.py`
- Create: `projects/server/tests/domain/test_dashboard.py`

**Interfaces:**
- Consumes: `domain.runs.events.RunEvent`, `EventType`; `domain.runs.run.Stage`.
- Produces:
  - `TokenPoint(BaseModel)`: `day: str`, `tokens: int`.
  - `ActivityItem(BaseModel)`: `id: str`, `type: str`, `description: str`, `agent_id: str | None = None`, `work_item_id: str | None = None`, `created_at: datetime`.
  - `build_token_series(events: list[RunEvent], today: date, days: int = 7) -> list[TokenPoint]`.
  - `to_activity_event(event: RunEvent) -> ActivityItem | None`.

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/domain/test_dashboard.py`:

```python
from datetime import UTC, date, datetime, timedelta

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
        _evt(EventType.STAGE_STARTED, when=datetime(2026, 7, 5, tzinfo=UTC)),             # no tokens
    ]
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/test_dashboard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.dashboard'`.

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/domain/dashboard.py`:

```python
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
_ACTIVITY_MAP: dict[EventType, tuple[str, "Callable[[RunEvent], str]"]] = {
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
```

Add the missing import for the type hint at the top (`from collections.abc import Callable`) so the annotation resolves, or drop the string annotation — simplest is to add:

```python
from collections.abc import Callable
```

near the top imports and change the `_ACTIVITY_MAP` annotation to `dict[EventType, tuple[str, Callable[[RunEvent], str]]]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/test_dashboard.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/dashboard.py projects/server/tests/domain/test_dashboard.py
git commit -m "feat: dashboard token-series + activity aggregators (RunEvent-backed)"
```

---

### Task 2: Routes — `GET /dashboard/token-usage` + `GET /activity`

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py`
- Create: `projects/server/src/interactors/api/routes/dashboard.py`
- Modify: `projects/server/src/interactors/api/routes/__init__.py`
- Create: `projects/server/tests/interactors/api/test_dashboard_api.py`

**Interfaces:**
- Consumes: `build_token_series`, `to_activity_event`, `TokenPoint`, `ActivityItem` (Task 1); `uow.run_events` (existing, owner-scoped `read_multi`, supports `created_at__gte` filter + `-created_at` order); `get_uow`; `crud_router.Envelope`/`ok`; `contract.iso`.
- Produces: `TokenPointOut{day, tokens}`, `ActivityEventOut{id, type, description, agentId, workItemId, createdAt}`; routes `GET /dashboard/token-usage` → `Envelope[list[TokenPointOut]]`, `GET /activity` → `Envelope[list[ActivityEventOut]]`; `dashboard_router`.

- [ ] **Step 1: Write the failing test**

Create `projects/server/tests/interactors/api/test_dashboard_api.py`:

```python
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
    _seed_event(session_factory, "dev-user", type_=EventType.RUN_STARTED, when=base - timedelta(minutes=3))
    _seed_event(session_factory, "dev-user", type_=EventType.LOG, when=base - timedelta(minutes=2))
    _seed_event(session_factory, "dev-user", type_=EventType.STAGE_PASSED, when=base - timedelta(minutes=1),
                role="engineer", stage=Stage.IMPLEMENT)
    rows = client.get("/activity").json()["data"]
    assert [r["type"] for r in rows] == ["agent_write", "status_change"]  # newest first, log dropped
    assert rows[0]["description"] == "engineer finished implement"


def test_activity_is_owner_scoped(client, client_other_owner, session_factory):
    _seed_event(session_factory, "dev-user", type_=EventType.RUN_STARTED, when=datetime.now(UTC))
    assert client_other_owner.get("/activity").json()["data"] == []
```

Note: reuse the existing `client`, `client_other_owner`, and `session_factory` fixtures in
`projects/server/tests/interactors/api/conftest.py` / the top-level conftest (the agents/attachments
tests already use this exact trio). `_seed_event` writes through an owner-scoped `SqlUnitOfWork` on
the shared `session_factory`; setting `created_at` explicitly on the DTO makes the repo persist that
timestamp (the base `create` keeps non-None fields), which the date-bucketing assertions rely on.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/api/test_dashboard_api.py -v`
Expected: FAIL — routes 404 / `TokenPointOut` import error.

- [ ] **Step 3: Write minimal implementation**

Add to `projects/server/src/interactors/api/contract.py` (near the other dashboard-ish models):

```python
class TokenPointOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    day: str
    tokens: int


class ActivityEventOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    description: str
    agentId: str | None = None
    workItemId: str | None = None
    createdAt: str
```

Create `projects/server/src/interactors/api/routes/dashboard.py`:

```python
from datetime import UTC, datetime, timedelta

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.dashboard import build_token_series, to_activity_event
from fastapi import APIRouter, Depends

from interactors.api.contract import ActivityEventOut, TokenPointOut, iso
from interactors.api.deps import get_uow

router = APIRouter(tags=["dashboard"])

TOKEN_WINDOW_DAYS = 7
ACTIVITY_LIMIT = 20
_ACTIVITY_SCAN = 40  # read extra so dropping `log`s still fills the list


@router.get("/dashboard/token-usage", response_model=Envelope[list[TokenPointOut]])
def token_usage(uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    now = datetime.now(UTC)
    cutoff = (now - timedelta(days=TOKEN_WINDOW_DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    events = uow.run_events.read_multi(
        filters={"created_at__gte": cutoff}, page_size=1000
    ).results
    series = build_token_series(events, now.date(), TOKEN_WINDOW_DAYS)
    return ok([TokenPointOut(day=p.day, tokens=p.tokens) for p in series])


@router.get("/activity", response_model=Envelope[list[ActivityEventOut]])
def activity(uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    events = uow.run_events.read_multi(
        order_by="-created_at", page_size=_ACTIVITY_SCAN
    ).results
    items = [it for it in (to_activity_event(e) for e in events) if it is not None]
    items = items[:ACTIVITY_LIMIT]
    return ok([
        ActivityEventOut(
            id=it.id, type=it.type, description=it.description,
            agentId=it.agent_id, workItemId=it.work_item_id,
            createdAt=iso(it.created_at),
        )
        for it in items
    ])
```

Register in `projects/server/src/interactors/api/routes/__init__.py`: add import
`from interactors.api.routes.dashboard import router as dashboard_router` and, inside
`register_routers`, `app.include_router(dashboard_router)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/interactors/api/test_dashboard_api.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Run the full backend suite + lint**

Run:
```bash
cd projects/server && uv run pytest -q
cd /Users/noel/projects/naaf/.worktrees/dashboard-widgets && make lint
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/api/contract.py projects/server/src/interactors/api/routes/dashboard.py projects/server/src/interactors/api/routes/__init__.py projects/server/tests/interactors/api/test_dashboard_api.py
git commit -m "feat: GET /dashboard/token-usage + GET /activity (RunEvent-backed)"
```

---

### Task 3: UI — poll + move handlers live

**Files:**
- Modify: `projects/ui/src/lib/api/hooks/useDashboard.ts`
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts`
- Create: `projects/ui/src/lib/api/hooks/useDashboard.test.tsx`

**Interfaces:**
- Produces: `DASHBOARD_POLL_MS = 10000`; `useTokenUsage`/`useActivity` poll on that interval; `/dashboard/token-usage` + `/activity` served by `liveHandlers`.

- [ ] **Step 1: Write the failing test**

Create `projects/ui/src/lib/api/hooks/useDashboard.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useActivity, useTokenUsage, DASHBOARD_POLL_MS } from "./useDashboard";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("exposes a dashboard poll interval", () => {
  expect(DASHBOARD_POLL_MS).toBe(10000);
});

test("useTokenUsage fetches the daily series", async () => {
  server.use(
    http.get("/api/dashboard/token-usage", () =>
      HttpResponse.json({ success: true, error: null,
        data: [{ day: "2026-07-05", tokens: 1200 }] }),
    ),
  );
  const { result } = renderHook(() => useTokenUsage(), { wrapper });
  await waitFor(() => expect(result.current.data).toHaveLength(1));
  expect(result.current.data?.[0].tokens).toBe(1200);
});

test("useActivity fetches recent activity rows", async () => {
  server.use(
    http.get("/api/activity", () =>
      HttpResponse.json({ success: true, error: null,
        data: [{ id: "e1", type: "agent_write", description: "engineer finished implement",
                  agentId: "engineer", workItemId: null, createdAt: "2026-07-05T00:00:00Z" }] }),
    ),
  );
  const { result } = renderHook(() => useActivity(), { wrapper });
  await waitFor(() => expect(result.current.data).toHaveLength(1));
  expect(result.current.data?.[0].type).toBe("agent_write");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test -- useDashboard`
Expected: FAIL — `DASHBOARD_POLL_MS` not exported.

- [ ] **Step 3: Write minimal implementation**

Edit `projects/ui/src/lib/api/hooks/useDashboard.ts` — add the constant and set `refetchInterval` on
the two widget hooks (leave `useDashboard()` — the metrics one — unchanged):

```ts
// The dashboard reflects server-side agent activity; poll while mounted so the
// token chart + activity feed stay live. Paused when the tab is hidden
// (refetchIntervalInBackground defaults to false).
export const DASHBOARD_POLL_MS = 10000;

export function useTokenUsage() {
  return useQuery({
    queryKey: [...queryKeys.dashboard(), "token-usage"],
    queryFn: () => apiFetch<TokenUsagePoint[]>("/dashboard/token-usage"),
    refetchInterval: DASHBOARD_POLL_MS,
  });
}

export function useActivity() {
  return useQuery({
    queryKey: [...queryKeys.dashboard(), "activity"],
    queryFn: () => apiFetch<ActivityEvent[]>("/activity"),
    refetchInterval: DASHBOARD_POLL_MS,
  });
}
```

In `projects/ui/src/lib/api/mocks/handlers.ts`, **move** the two handlers from `mockOnlyHandlers`
into `liveHandlers`. Delete these two lines (and their `// ── Dashboard` / `// ── Activity` comment
headers if they solely head these) from the `mockOnlyHandlers` array:

```ts
http.get(`${BASE}/dashboard/token-usage`, () => ok(seed.tokenUsagePoints)),
...
http.get(`${BASE}/activity`, () => ok(seed.activityEvents)),
```

and add the identical two lines into the `liveHandlers` array (any position — literal paths). Bodies
unchanged. Leave `/dashboard/metrics` and `/budget` in `mockOnlyHandlers`. This makes live mode pass
these two through to the backend while mock mode still renders the fixtures.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test -- useDashboard`
Expected: PASS.

- [ ] **Step 5: Run the full UI suite + lint + build**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm build`
Expected: all green. (The `TokenChart`/`ActivityFeed` component tests still pass — the mock fixtures
and component rendering are unchanged; only the handler bucket moved.)

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/lib/api/hooks/useDashboard.ts projects/ui/src/lib/api/hooks/useDashboard.test.tsx projects/ui/src/lib/api/mocks/handlers.ts
git commit -m "feat: poll token-usage + activity, move both endpoints live-backed"
```

---

### Task 4: Gates, docs, and PR

**Files:**
- Modify: `docs/project-history.md`

- [ ] **Step 1: Run all gates**

Run:
```bash
cd /Users/noel/projects/naaf/.worktrees/dashboard-widgets
make coverage   # 80% gate
make lint
cd projects/ui && pnpm test && pnpm lint && pnpm build
```
Expected: coverage ≥ 80%, lint clean, UI green + builds. If backend coverage dips, add a targeted
aggregator test (e.g. `build_token_series` with an event exactly on the oldest window day).

- [ ] **Step 2: Update project history**

Add a dated entry to `docs/project-history.md` (top of the `## Status (2026-07-05)` section, or add
that heading above the latest one) summarizing: the dashboard TokenChart + ActivityFeed are now
live — `GET /dashboard/token-usage` buckets per-stage `RunEvent` token deltas into a 7-day series,
`GET /activity` maps recent cross-run RunEvents to activity rows (log excluded, ≤20, newest-first),
both owner-scoped + polled every 10s; components unchanged; ActivityFeed re-pointable at
`agent_events` when stream-agent-output lands; `/dashboard/metrics` stays mocked. Link the spec + plan.

- [ ] **Step 3: Commit docs**

```bash
git add docs/project-history.md
git commit -m "docs: record dashboard token-chart + activity-feed feature"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/dashboard-token-activity
gh pr create --title "feat: wire the dashboard token chart + activity feed to real data" --body "$(cat <<'EOF'
## Summary
- Two pure domain aggregators over the owner's `RunEvent` stream: `build_token_series` buckets per-stage token deltas (`payload["tokens"]` on stage_passed/failed) into a 7-day zero-filled series; `to_activity_event` maps events to activity rows (`log` dropped as noise).
- New owner-scoped `GET /dashboard/token-usage` and `GET /activity` (`routes/dashboard.py`) — read-only aggregation, **no new table/migration**.
- UI: `useTokenUsage`/`useActivity` poll every 10s (paused when hidden); both handlers moved from MSW mock-only to live-backed. The TokenChart/ActivityFeed components are unchanged (shapes match).
- **Deferred:** ActivityFeed re-points at the richer `agent_events` trace when `stream-agent-output` ships; `/dashboard/metrics` stays mocked; per-model token pricing (A5d).

Design: `docs/superpowers/specs/2026-07-05-dashboard-token-activity-design.md` · Plan: `docs/superpowers/plans/2026-07-05-dashboard-token-activity.md`

## Test plan
- [x] `make coverage` ≥ 80% · `make lint` clean
- [x] `cd projects/ui && pnpm test && pnpm build` green
- [x] Aggregators: 7-day zero-fill, per-day token sum, out-of-window/no-token ignored, each activity-type mapping, log→None, role/stage fallbacks
- [x] Routes: token-usage 7 points summed per day + owner-scoped; activity newest-first, log excluded, ≤20, owner-scoped
- [ ] Manual: `make dev`, run a task through the pipeline, watch the token chart bar for today grow and the activity feed list stage events within ~10s
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**
- TokenChart daily series from RunEvent token deltas, 7-day zero-filled → Task 1 `build_token_series` + Task 2 route. ✓
- ActivityFeed mapping (each type + log→None + fallbacks), newest-first, ≤20, owner-scoped → Task 1 `to_activity_event` + Task 2 route. ✓
- `routes/dashboard.py` hosts both (avoids `activity.py` clash) + contract models + registration → Task 2. ✓
- Read-only, no table/migration → Tasks 1–2 are pure reads. ✓
- UI poll (`DASHBOARD_POLL_MS=10000`, hidden pause) + handlers moved live, components unchanged → Task 3. ✓
- `/dashboard/metrics` stays mocked → not touched. ✓
- Deferred (agent_events re-point, metrics, pricing, work_item_id null) → noted, not implemented. ✓

**2. Placeholder scan:** No TBD/TODO/"add validation". The `Callable` import note in Task 1 Step 3 is a concrete fix instruction, not a placeholder. Route/aggregator code is complete.

**3. Type consistency:** `TokenPoint`/`ActivityItem` (domain, snake) → `TokenPointOut`/`ActivityEventOut` (contract, camel) → UI `TokenUsagePoint`/`ActivityEvent` (existing schema) align: `day/tokens`; `id/type/description/agent_id→agentId/work_item_id→workItemId/created_at→createdAt`. `build_token_series(events, today, days=7)` and `to_activity_event(event)` signatures identical across Tasks 1–2. `DASHBOARD_POLL_MS=10000` consistent in Task 3 impl + test. Activity `type` values match the existing `ActivityEvent` union (`agent_write|status_change|run_complete|run_failed`).
