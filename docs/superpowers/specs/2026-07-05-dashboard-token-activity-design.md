# Dashboard TokenChart + ActivityFeed — design

> Status: approved for planning · 2026-07-05
> Feature: replace the two remaining mocked dashboard widgets — the **TokenChart**
> (daily token usage) and the **ActivityFeed** (recent activity) — with real data
> derived from `RunEvent`s. Read-only aggregation; no new table or migration.

## Goal

The dashboard's TokenChart and ActivityFeed are the last two `mockOnly` widgets (the live-agents
work already wired the running-agents panel + active-agents count). Back them with real data so a
user sees actual daily token usage and recent agent activity across all their runs.

Both are backed by the existing **`RunEvent`** stream (owner-scoped, cross-run). No new persistence.

## Key decisions (from brainstorming)

- **Both widgets now**, backed by **`RunEvent`s** (not `agent_events`, not `/notifications`).
- The `stream-agent-output` feature (design-only, unbuilt) introduces a richer `agent_events`
  activity trace; when it ships, the ActivityFeed can be **re-pointed** at that source. Until then,
  RunEvents are the source of truth. (Deferred, noted below.)
- Read-only aggregation via **pure domain functions** (portable, testable) — no JSON-in-SQL.
- Both endpoints move from MSW `mockOnly` to live-backed; the **components are unchanged** (same
  props/rendering) — only the endpoints and the hooks' polling change.
- `/dashboard/metrics` (the other mock-only endpoint) stays mocked — out of scope.

## Data sources (verified)

- `RunEvent(Entity)` — `owner_id, run_id, seq, global_seq, stage, role, type: EventType, payload,
  created_at`. Owner-scoped `read_multi` (default order `-created_at`) supports `__gte` filters.
- Per-stage **token deltas** already ride in event payloads: `_finish_stage`
  (`interactors/worker/handlers.py`) emits `stage_passed`/`stage_failed` with
  `payload={"summary": …, "tokens": <delta>}`.
- `EventType`: `run_started, stage_started, log, stage_passed, stage_failed, gate_requested,
  gate_resolved, run_finished`.

## 1. Domain aggregators — `domain/dashboard.py` (new, pure)

```
def build_token_series(events: list[RunEvent], today: date, days: int = 7) -> list[TokenPoint]
def to_activity_event(event: RunEvent) -> ActivityItem | None
```

- `TokenPoint(BaseModel)`: `day: str  # YYYY-MM-DD`, `tokens: int`.
- `ActivityItem(BaseModel)`: `id: str`, `type: str`, `description: str`, `agent_id: str | None`,
  `work_item_id: str | None`, `created_at: datetime`.

### `build_token_series`

- Produces exactly `days` points, one per calendar day ending at `today` (oldest→newest), each
  zero-initialized.
- For each event, add `int(event.payload.get("tokens", 0) or 0)` to the bucket for
  `event.created_at.date()` **if that date is within the window** (events outside the window, or
  with no `tokens` key, contribute 0). Only `stage_passed`/`stage_failed` carry tokens; the guard
  `payload.get("tokens")` naturally ignores the rest.
- Deterministic, pure, no I/O.

### `to_activity_event`

Maps a `RunEvent` to an `ActivityItem`, returning `None` for events that shouldn't appear (noise):

| `RunEvent.type` | activity `type` | `description` |
|---|---|---|
| `run_started` | `status_change` | `Run started` |
| `stage_started` | `status_change` | `{role} started {stage}` |
| `stage_passed` | `agent_write` | `{role} finished {stage}` |
| `stage_failed` | `run_failed` | `{stage} failed` |
| `gate_requested` | `status_change` | `Gate requested ({stage})` |
| `gate_resolved` | `status_change` | `Gate resolved ({stage})` |
| `run_finished` | `run_complete` | `Run finished` |
| `log` | — | **None (skipped)** |

- `agent_id = event.role`; `work_item_id = None` (optional; avoids an N+1 run→work-item lookup —
  the component doesn't require it).
- `{role}` falls back to `"agent"` when `event.role` is None; `{stage}` uses `event.stage.value`
  (falls back to `""` when None).
- The activity `type` values (`agent_write | status_change | run_complete | run_failed`) match the
  existing `ActivityEvent` contract the UI already renders.

## 2. Routes — `routes/dashboard.py` (new)

One module hosts both read endpoints (kept out of a `routes/activity.py` filename to avoid a future
clash with `stream-agent-output`'s planned `routes/activity.py`). Both owner-scoped via `get_uow`.

- `GET /dashboard/token-usage` → `Envelope[list[TokenPointOut]]`
  - Reads the owner's `run_events` since the window cutoff:
    `uow.run_events.read_multi(filters={"created_at__gte": cutoff}, page_size=1000)` where
    `cutoff = today - 6 days` (7-day inclusive window), runs `build_token_series(events, today, 7)`,
    maps to `TokenPointOut{day, tokens}`.
  - `today` = server "today" (`datetime.now(UTC).date()`).
- `GET /activity` → `Envelope[list[ActivityEventOut]]`
  - Reads the owner's most-recent cross-run events:
    `uow.run_events.read_multi(order_by="-created_at", page_size=40).results`, maps each via
    `to_activity_event`, drops `None`s, truncates to **20**, returns them (newest-first).
  - Reading 40 and keeping ≤20 after dropping `log`s leaves headroom so the feed still fills when
    recent events include noise.

New contract models (camelCase): `TokenPointOut{day, tokens}`, `ActivityEventOut{id, type,
description, agentId, workItemId, createdAt}` — matching the shapes the UI hooks already expect.
Registered in `interactors/api/routes/__init__.py`.

## 3. UI

- `useTokenUsage` and `useActivity` (`lib/api/hooks/useDashboard.ts`) gain a `refetchInterval`
  (`DASHBOARD_POLL_MS = 10000`), paused when the tab is hidden (React Query default
  `refetchIntervalInBackground: false`) — consistent with the board/live-agents polling.
- The `/dashboard/token-usage` and `/activity` handlers move from `mockOnlyHandlers` to
  `liveHandlers` in `mocks/handlers.ts` (bodies unchanged — `ok(seed.tokenUsagePoints)` /
  `ok(seed.activityEvents)` — so mock mode still renders; live mode passes through to the backend).
- **`TokenChart` and `ActivityFeed` components are unchanged** — the contract shapes match, so no
  component edits are needed.

## 4. Testing (TDD)

- **Aggregators (`domain/dashboard.py`):**
  - `build_token_series`: returns exactly 7 zero-filled points oldest→newest; sums `payload["tokens"]`
    into the correct day; ignores events outside the window and events without a `tokens` key;
    multiple events same day accumulate.
  - `to_activity_event`: each `EventType` maps to the right `type`/`description`; `log` → `None`;
    `role`/`stage` None fallbacks.
- **Routes:**
  - `GET /dashboard/token-usage`: 7 points, tokens summed per day from seeded run_events,
    owner-scoped (other owner's events excluded).
  - `GET /activity`: newest-first, cross-run, `log` events excluded, capped at 20, owner-scoped.
- **UI (vitest):** `useTokenUsage`/`useActivity` set `DASHBOARD_POLL_MS`; both handlers resolve
  live-shaped envelopes; TokenChart/ActivityFeed still render from the (unchanged) fixtures.
- **Gates:** `make coverage` (80%) + `make lint`; UI `pnpm test` + `pnpm lint` + `pnpm build`.

## Out of scope / deferred

- Re-pointing the ActivityFeed at the richer `agent_events` trace once `stream-agent-output` ships
  (the RunEvent-backed feed is designed to be swappable behind the same `/activity` contract).
- `/dashboard/metrics` stays mocked.
- Real per-model token pricing / cost (A5d).
- `work_item_id` on activity rows (left null to avoid an N+1; can be batch-resolved later if the UI
  wants clickable rows).
- A global SSE push for these widgets — polling is sufficient (daily buckets + recent list).
