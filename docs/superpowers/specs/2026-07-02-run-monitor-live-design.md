# Run Monitor Live + Run Usage Tracking (Design)

**Date:** 2026-07-02
**Status:** Approved (design) — ready for implementation plan
**Phase:** A3 UI follow-up + a small A5d usage slice pulled forward

## Summary

Wire the UI **run monitor** (the Detail screen's Agent-Monitor tab: header, step
timeline, log stream) to the **live A3 run API**, and give runs **token/cost tracking**
so the monitor's usage display is real. The mock-era `AgentRun`/`RunStep`/`LogLine`
shapes diverge from the live `RunOut`/`RunEventOut`; the UI **adopts the live shapes** as
the source of truth. The monitor gains a **gate Approve/Reject** control (the live
pipeline pauses at plan/merge gates and needs resolution to progress).

This is a full-stack slice with two sequenced halves:
1. **Backend** — track `token_usage` on a `Run`, accumulated from per-stage runtime
   output; expose `tokenUsage` + derived `cost` on `RunOut`.
2. **Frontend** — the run monitor consumes `RunOut`/`RunEventOut` (live + SSE), renders
   stages/events/usage/status/timestamps, and resolves gates.

## Background & motivation

The A3 run pipeline is built and live (`GET /runs`, `GET /runs/{id}` → `RunOut`,
`GET /runs/{id}/events` + SSE `/events/stream` → `RunEventOut`,
`POST /runs/{id}/gate`, `POST /work-items/{id}/runs`). But the UI run monitor still
renders **mock** data in shapes that don't match the live contract:

| Concern | Mock (`AgentRun`) | Live (`RunOut`) |
|---|---|---|
| Progress unit | `steps: RunStep[]` (`Plan/Read/Analyze/Generate/Test/PR`, `done/active/pending`) | `stages: StageStateOut[]` (`plan/provision/implement/verify/pr/learn`, `pending/running/passed/failed/skipped/gated`) |
| Logs | inline `logLines: LogLine[]` | separate `GET /runs/{id}/events` → `RunEventOut` |
| Live stream | SSE `/runs/{id}/stream` → `LogLine` | SSE `/runs/{id}/events/stream` → `RunEventOut` |
| Status enum | `running/paused/complete/failed` | `queued/running/awaiting_gate/succeeded/failed/cancelled` |
| Gates | (none) | `pendingGate: GateOut` + `POST /gate` |
| Agent identity | `agentId` → mock `Agent` lookup | stage `role` (no live `Agent` entity) |
| Usage | `tokenUsage`, `cost` | **absent** — added by this slice |

The run monitor is the natural next slice: it makes the already-built A3 pipeline
observable and controllable from the UI, following the same playbook as the messaging
foundation (adopt the live contract; move MSW handlers behind `VITE_LIVE_API`; retire the
diverged mock shapes).

## Goals

1. Runs track token usage; `RunOut` exposes `tokenUsage` and a derived `cost`.
2. The run monitor renders a live run: header (agent role, status, current stage,
   timestamps, token/cost), stage timeline, and event/log stream (history + SSE).
3. The monitor surfaces a pending gate with **Approve / Reject**, wired to
   `POST /runs/{id}/gate`.
4. The monitor works against the real backend under `VITE_LIVE_API`, and still renders
   in the default fully-mocked demo (mock fixtures reshaped to the live contract).

## Non-Goals (explicitly out of scope / stay mocked)

- The `Agent` entity (`/agents`) and anything that consumes it: the **dashboard
  "Running Agents" panel** and the **board "Live Agents" ribbon**. A live agent-as-entity
  is a later monitoring/A5 concern.
- Real per-model token pricing and a usage/billing UI (full A5d). This slice tracks a
  raw token count and derives cost from a single flat placeholder rate.
- Starting a run from the monitor. The Detail screen currently has no start-run trigger;
  runs are started via the API/seed and the monitor **observes** them. (`POST
  /work-items/{id}/runs` already exists and is untouched.)
- Real token counts from an LLM — `FakeAgentRuntime` emits deterministic placeholder
  tokens until the A5 runtime lands.

## Architecture

### Backend — run usage tracking

Follows the hexagonal layering already in `domain/runs`, `adapters/database`,
`interactors/worker`, `interactors/api`.

- **Domain (`domain/runs/run.py`):** `Run` gains `token_usage: int = 0`. Cost is **not**
  stored — it is derived at the contract layer (single source of truth: `token_usage`).
- **Runtime contract (`domain/agent/runtime.py`):** `StageResult` gains `tokens: int = 0`.
- **Fake runtime (`adapters/agent/runtime/fake.py`):** `run_stage` returns a deterministic
  `tokens` per stage — derived from the scripted step count for that stage (a fixed
  `TOKENS_PER_STEP` constant × number of steps), so totals are stable for tests and climb
  visibly across a run.
- **Accumulation (`interactors/worker/handlers.py`):** in `_run_stage_inline`, when a
  stage completes, fold the stage's tokens onto the run immutably —
  `run = run.model_copy(update={"token_usage": run.token_usage + outcome.result.tokens})`
  — persist via the run repository, and include `tokens` in the `STAGE_PASSED` event
  payload (`payload={"summary": ..., "tokens": ...}`).
- **Persistence (`adapters/database/orm.py` + migration `0008`):** `RunRow` gains a
  `token_usage` column (`Integer`, default 0). Alembic `0008_run_token_usage`
  (`down_revision = "0007_messages"`).
- **Contract (`interactors/api/contract.py`):** `RunOut` gains `tokenUsage: int` (from
  `run.token_usage`) and `cost: float` (derived — see below). The `_run_out` mapper in
  `routes/runs.py` populates both.

**Cost derivation.** A module-level constant `COST_PER_1K_TOKENS: float` (documented as a
flat placeholder; real per-model pricing is A5). `cost = round(token_usage / 1000 *
COST_PER_1K_TOKENS, 4)`. Computed in the `RunOut` mapper. No stored cost column, no
per-model pricing.

### Frontend — run monitor

The UI adopts the live `RunOut`/`RunEventOut`/`StageStateOut`/`GateOut` shapes.

- **Types (`lib/api/schema.d.ts`):** add `RunOut`, `RunEventOut`, `StageStateOut`,
  `GateOut` (matching the backend contract, camelCase). Retire the mock `AgentRun`,
  `RunStep`, `LogLine` (used only by the run monitor). `Agent` stays (mocked panels).
- **Hooks (`lib/api/hooks/`):**
  - `useWorkItemRun(itemId)` → `GET /runs?work_item={id}`, newest first, returns the latest
    `RunOut | null` (replaces the mock `/work-items/{id}/run`).
  - `useRun(runId)` → `GET /runs/{id}` (`RunOut`) + event history `GET /runs/{id}/events`
    + SSE `GET /runs/{id}/events/stream?after={lastSeq}` (`RunEventOut`). Exposes
    `{ run, events, isStreaming }`. Reuses the existing `useEventSource`.
  - `useResolveGate(runId)` → `POST /runs/{id}/gate { decision }`; invalidates
    `queryKeys.run(runId)` on success.
- **Components (`modules/detail/`):**
  - `AgentMonitor` renders `RunOut`: header shows the **current stage's `role`** as the
    agent label (no `useAgents`), plus **status, current stage, and timestamps** (run
    `startedAt`/`updatedAt`, current stage `startedAt`), and the **token/cost** readout
    (`run.tokenUsage`, `run.cost`). When `run.pendingGate` is set, show an **Approve /
    Reject** control wired to `useResolveGate`.
  - `StepTimeline` renders `RunOut.stages` (`StageStateOut`): the six pipeline stages with
    circle states mapped from status (`passed→done`, `running→active`, `gated→active/gate`,
    `pending/skipped→pending`, `failed→failed`). Stage label from `stage`.
  - `LogStream` renders `RunEventOut[]`: one line per event — `createdAt` timestamp, a
    `stage`/`role` tag, and a message derived from `type` + `payload` (e.g. `log` →
    `payload.message`; `stage_passed` → `"✓ {stage} ({payload.tokens} tok)"`;
    `gate_requested` → `"⏸ gate: {payload.kind}"`; `run_finished` → `payload.status`).
- **Detail screen (`modules/detail/DetailScreen.tsx`):** unchanged flow —
  `useWorkItemRun(itemId)` → `<AgentMonitor runId={run.id} />` — now backed by `RunOut`.

### Mocks / flag / retirement

- Reshape the run **mock fixtures + handlers** so the default (no-`VITE_LIVE_API`) demo
  still renders the monitor: `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events`,
  SSE `/runs/{id}/events/stream`, `POST /runs/{id}/gate` all return `RunOut`/`RunEventOut`
  shapes. Move these handlers into `liveHandlers` (bypass to the real backend under
  `VITE_LIVE_API`).
- Retire the mock `/work-items/{id}/run` (singular) and `/runs/{id}/stream` handlers, and
  the `AgentRun`/`RunStep`/`LogLine` fixtures.
- Keep mocked: `/agents`, the dashboard "Running Agents" panel, the board "Live Agents"
  ribbon.

## Data flow (a live run in the monitor)

1. User opens a work item's Detail screen → `useWorkItemRun` fetches the latest `RunOut`.
2. `AgentMonitor(runId)` mounts → `useRun` fetches `RunOut` + event history, then opens the
   SSE stream from `after = last seen seq`.
3. As the worker advances the run, it writes `RunEvent`s (and accumulates `token_usage`);
   the SSE pushes each new `RunEventOut`; `LogStream` appends, `StepTimeline` reflects
   stage changes on `RunOut` refetch/invalidation, and the token/cost readout climbs.
4. At a plan/merge gate, `RunOut.pendingGate` is set and `status = awaiting_gate`; the
   monitor shows Approve/Reject → `POST /gate` → run resumes; the monitor invalidates and
   re-streams.
5. The SSE closes on `run_finished`.

## Error handling

- Backend: gate/run endpoints already return owner-scoped 404 and the standard envelope;
  unchanged. `token_usage` accumulation is inside the existing per-stage transaction.
- Frontend: `useRun` surfaces a load error state; a missing run (`useWorkItemRun` →
  `null`) shows the existing "no run" empty state; a gate resolve failure surfaces inline
  and leaves the run untouched (server is source of truth; refetch reconciles). SSE is
  best-effort (jsdom-guarded, as today).

## Testing

TDD; ≥80% backend coverage gate; UI vitest + shared MSW server; pristine output.

**Backend (pytest, SQLite in-memory):**
- `Run` carries `token_usage` (default 0); immutable accumulation via `model_copy`.
- Handler accumulation: a run's `token_usage` is the sum of its stages' tokens after a
  full pipeline; `STAGE_PASSED` payload carries `tokens`.
- `FakeAgentRuntime` returns deterministic per-stage `tokens`.
- `RunOut` exposes `tokenUsage` and derived `cost` (= `token_usage/1000 ×
  COST_PER_1K_TOKENS`), including the zero case.
- Migration `0008` creates the `runs.token_usage` column.

**Frontend (vitest + MSW):**
- `useWorkItemRun` returns the latest run from `GET /runs?work_item=`; `null` when none.
- `useRun` merges event history + a streamed event; `isStreaming` reflects status.
- `useResolveGate` posts and invalidates.
- `StepTimeline` renders live `stages` with correct circle states; `LogStream` renders
  `RunEventOut` lines (incl. a `stage_passed` token line and a gate line).
- `AgentMonitor` renders status/current-stage/timestamps + token/cost, and shows +
  resolves a pending gate (Approve/Reject → invalidate).
- MSW live-vs-mock split: the run endpoints honour `VITE_LIVE_API`.

## Rollout / sequencing

Backend first (the UI displays what the backend tracks):
1. `Run.token_usage` + `StageResult.tokens` + `FakeAgentRuntime` tokens (domain/runtime).
2. Handler accumulation + `STAGE_PASSED` token payload.
3. `RunRow.token_usage` column + migration `0008`.
4. `RunOut` `tokenUsage` + derived `cost` + `COST_PER_1K_TOKENS`.
5. Frontend: schema types (add `RunOut`/`RunEventOut`/`StageStateOut`/`GateOut`; retire
   mock run shapes) + hooks (`useWorkItemRun`, `useRun`, `useResolveGate`).
6. Frontend: `StepTimeline`, `LogStream`, `AgentMonitor` (incl. gate UI + usage +
   status/stage/timestamps).
7. Frontend: reshape run mock fixtures/handlers to the live contract; move to
   `liveHandlers`; retire the dead mock run surface.

Each step is independently testable; the default-mock demo stays working throughout.

## Open questions

None blocking. `COST_PER_1K_TOKENS` and `TOKENS_PER_STEP` are documented placeholder
constants defined in the plan; real per-model pricing and LLM token counts arrive with A5.
