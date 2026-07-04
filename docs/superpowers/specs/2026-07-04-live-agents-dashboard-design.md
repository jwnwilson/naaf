# Live agents on the dashboard — design

> Status: approved for planning · 2026-07-04
> Feature: replace the mocked dashboard "running agents" panel with real data —
> show which team roles are live and running, driven by active runs.

## Goal

The dashboard's **RunningAgentsPanel** (and the "ACTIVE AGENTS" metric count) currently render
from MSW mock data with no backend. Wire them to real data so a user can see, at a glance, which
**team roles are live and running** right now.

There is no persisted agent-runtime entity in the backend. The real signal is **active runs**: a
run drives roles sequentially (lead plans → engineer implements → qa verifies), so at any instant a
run's currently-running stage has exactly one role. This feature aggregates the enabled
`AgentDefinition` roster with active runs into a role-oriented "live agents" list, served by a new
backend endpoint and polled by the UI.

## Key decisions (from brainstorming)

- **A "live agent" = a team role** from the enabled `AgentDefinition` roster, shown as **running**
  (an active run's current stage is that role) or **idle**. One row per role.
- **The roster↔run join happens on the backend** — a new `GET /agents` endpoint (replacing the
  mock), backed by a pure domain aggregator.
- **Refresh by polling** — React Query `refetchInterval` (~5s, paused when the tab is hidden),
  mirroring the existing board-poll pattern. No global SSE stream (only per-run SSE exists today;
  building a cross-run stream is deferred as overkill for a role roster).
- **Scope**: the live-agents panel **and** the "ACTIVE AGENTS" metric count. TokenChart,
  ActivityFeed, and the other metric cards stay mocked (separate A5d/activity concerns).

## Role mapping

The pipeline dispatches three stage-roles — `lead`, `engineer`, `qa` — while the roster uses the
full `AgentRole` enum (`lead`, `architect`, `backend`, `frontend`, `qa`, `devops`, `custom`). The
canonical stage-role → roster-role map:

| stage-role | roster `AgentRole` |
|---|---|
| `lead` | `lead` |
| `engineer` | `backend` |
| `qa` | `qa` |

Architect/frontend/devops roster rows exist but the current pipeline never runs them, so they
remain idle. A run's **current role** is the `role` of its currently-running `StageState` (the
`StageState` whose `stage == run.current_stage`); fallback to a fixed `Stage → stage-role` map
(`plan`/`provision`/`pr`/`learn → lead`, `implement → engineer`, `verify → qa`) if no running
stage carries a role.

## Data model — `AgentOut` contract

One row per enabled roster role (camelCase, wrapped in the standard `{success, data, error}`
envelope):

```
AgentOut {
  role: str                  # AgentRole value: lead | architect | backend | frontend | qa | devops
  model: str                 # AgentDefinition.model_alias ("" if unset)
  status: "running" | "idle"
  runId: str | null          # the active run driving this role (when running)
  workItemId: str | null     # the work item that run is on
  currentStage: str | null   # Stage value of the run's current stage (when running)
  progress: float | null     # stages passed / total pipeline stages (when running), else null
  tokenUsage: int            # the active run's token_usage when running, else 0
}
```

Rows are returned in a **fixed role order** for stable display: `lead, architect, backend,
frontend, qa, devops` (any roster role outside this list, e.g. `custom`, sorts last). The TS type is
hand-defined in the UI hook (as the attachments feature did) to avoid an OpenAPI regeneration step.

## Backend

### Pure domain aggregator — `domain/live_agents.py`

```
STAGE_ROLE_TO_AGENT_ROLE: dict[str, AgentRole]   # lead→LEAD, engineer→BACKEND, qa→QA
STAGE_TO_STAGE_ROLE: dict[Stage, str]            # plan/provision/pr/learn→lead, implement→engineer, verify→qa

class LiveAgent(BaseModel):   # domain value object
    role: AgentRole
    model: str
    status: Literal["running", "idle"]
    run_id: str | None
    work_item_id: str | None
    current_stage: Stage | None
    progress: float | None
    token_usage: int

def build_live_agents(definitions: list[AgentDefinition], active_runs: list[Run]) -> list[LiveAgent]
```

- Builds a base roster row per enabled `AgentDefinition` (status `idle`, `token_usage=0`, nulls).
- For each active run, resolves its current stage-role → `AgentRole` and, if a roster row for that
  role exists, marks it **running** with the run's `id`, `work_item_id`, `current_stage`, derived
  `progress` (count of `StageState` with `status == passed` / total pipeline stage count), and
  `token_usage`.
- If a role has more than one active run, the **most-recently-started** run wins (by
  `started_at`, falling back to `created_at`). This is the "one row per role" trade-off — concurrent
  same-role runs collapse to one row.
- No I/O; pure over domain models. Fully unit-testable.

### Route — `routes/agents.py`

- `GET /agents` → `Envelope[list[AgentOut]]`. Owner-scoped via `get_uow`.
- Reads `uow.agent_definitions.read_multi(filters={"enabled": True})` (the roster) and
  `uow.runs.read_multi(filters={"status__in": ["running", "awaiting_gate"]})` (active runs), calls
  `build_live_agents`, and maps `LiveAgent → AgentOut`.
- Registered in `interactors/api/routes/__init__.py` (`app.include_router(agents_router)`).

### Notes

- `awaiting_gate` counts as running (the role is live, just paused on a human gate).
- No new persistence, no migration — pure read aggregation over existing tables.

## Refresh — polling

`useAgents` gains a React Query `refetchInterval` of `AGENTS_POLL_MS` (~5000ms), paused when the
document is hidden (same approach as `useBoard`/`BOARD_POLL_MS`). No SSE.

## UI changes

- **`RunningAgentsPanel`** — consume the new `AgentOut` shape. Running rows: role · work item
  (`workItemId`) · current stage · a `ProgressBar` from `progress` · `tokenUsage`. Idle rows: role ·
  `model`. Split by `status === "running"`; header count = running rows. The non-wired "Pause"/
  "Assign" buttons are dropped (no backend action exists) — rows are read-only status.
- **`MetricCards`** "ACTIVE AGENTS" card — derive the number from `useAgents()` (count of running
  rows) rather than the mocked `/dashboard/metrics.activeAgents`. The other cards keep using
  `useDashboard()`/`useBudget()` as-is.
- **`useAgents`** — hand-defined `Agent`/`AgentOut` TS type (role-oriented), `refetchInterval` +
  hidden-tab pause.
- **Mocks** — reshape the `/agents` handler and `seed.agents` fixture to the new role-row shape, and
  move the `/agents` handler from `mockOnlyHandlers` to `liveHandlers` (so live mode hits the real
  backend; mock mode still renders the reshaped fixtures). Seed a mix of running + idle roles so the
  panel is demoable offline.

## Testing

- **Backend — aggregator (`domain/live_agents.py`)**: all roster rows idle when no active runs; a
  running `implement` stage lights up the `backend` row (engineer→backend mapping); `lead`/`qa`
  mappings; `awaiting_gate` run counts as running; two active runs on the same role → one row, the
  most-recently-started wins; progress = passed/total; a run whose role has no roster row lights up
  nothing.
- **Backend — route (`GET /agents`)**: envelope shape; owner-scoping (only the caller's roster +
  runs); running vs idle rows reflect seeded runs; empty roster → empty list.
- **UI**: `RunningAgentsPanel` renders running + idle rows from the new shape and the correct active
  count; `MetricCards` "ACTIVE AGENTS" equals the running-row count; `useAgents` sets the poll
  interval. All against MSW with the reshaped fixtures.

## Out of scope / deferred

- Global/cross-run SSE stream (polling chosen instead).
- TokenChart (token time-series), ActivityFeed (cross-run activity), and the non-agent metric cards
  — remain mocked.
- Agent actions (pause/assign) — no backend action exists; rows are read-only.
- Persisted agent-runtime entity — not introduced; the roster + active runs are the source of truth.
