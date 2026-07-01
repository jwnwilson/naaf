# A3 — Agent Run Pipeline (Local-First, FakeAgentRuntime) — Design

**Date:** 2026-06-30
**Status:** Approved design, pending implementation plan
**Milestone:** A3 (the run pipeline spine)
**Builds on:** A1 control plane + A2 UI + A2-4 live API — all merged to `main`.

## 1. Problem & goal

NAAF can model projects/work-items/teams and show them in a live UI, but **nothing runs** — "hit Run, watch a team produce a result" doesn't exist. A3 builds the **orchestration spine**: starting a run on a work-item drives it through the agent pipeline `PLAN → PROVISION → IMPLEMENT → VERIFY → PR → LEARN` with human gates, persisting a run with a stage timeline and an append-only event stream, all exercised by **scripted fake agents** over a **durable Local-First message bus**. The mocked **Runs**, **Agent-Monitor**, and **inbox** UI screens go live.

### Success criterion

> `POST /work-items/{id}/runs` starts a run; a separate **worker** process drives `PLAN → [✋plan gate] → IMPLEMENT → VERIFY → [✋merge gate] → PR → LEARN` via the durable bus with `FakeAgentRuntime` agents; a `Run` with a stage timeline + append-only `RunEvent`s persists; gates pause the run and resolve via the API (surfacing in the inbox); the work-item status tracks progress; and it is all observable over the run API + a live **SSE** event stream. `make coverage` (80%) + `make lint` green.

## 2. Scope

**In:** durable Postgres message bus (`MessageBus` port + impl); worker process (`make worker`) with a testable `process_next`; `Run`/`RunEvent`/`Gate` domain model + the pure stage state machine; `AgentRuntime` port + `FakeAgentRuntime`; lead/engineer/QA agent message-handlers + orchestration; human gates (pause/resume); Run/RunEvent persistence + migration; the run API (start/get/list/events/gate) + **SSE**; work-item status coupling; contract alignment so the UI Runs/Agent-Monitor/inbox screens go live.

**Out (later milestones):** real LLM / Claude Code runtime + LiteLLM → **A5**; sandbox / egress proxy / GitHub App / real PRs → **A4**; refinement chat + memory/curator → **A6**. Therefore `PROVISION`, `PR`, `LEARN` are **stub stages** (emit events + advance, no real sandbox/GitHub/memory); `PLAN`, `IMPLEMENT`, `VERIFY` are driven by `FakeAgentRuntime`. No real-time cost/budget enforcement (A5d). Architect role / parallel engineers / cross-model review → Phase B; A3 uses the A1 default team (lead + engineer + QA).

## 3. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| A3 ambition | **Full spine**: durable bus + stages + gates, fakes only | The real foundation A4/A5 plug into; faithful to the Local-First design |
| Bus + executor | **Postgres-backed durable bus + separate worker process** | Survives restarts and carries into A4 unchanged (real containers poll the same bus) |
| Event delivery | **SSE streaming now** (+ cursor polling underneath) | The Agent-Monitor's "live logs" are a core demo; poll-based tail keeps it simple |
| Stage fidelity | `PLAN/IMPLEMENT/VERIFY` via `FakeAgentRuntime`; `PROVISION/PR/LEARN` stubbed | Those stubs need A4/A5/A6 infra not yet built |
| Orchestration | Lead agent orchestrates other agents via per-agent bus queues | Master design §2/§3 Local-First; team lead is the orchestrator |

## 4. Architecture — the Local-First substrate

Four cooperating pieces; domain stays pure; everything owner-scoped.

### 4.1 Durable message bus (`adapters/bus/`, Postgres)
A `MessageBus` **port** (placed with its impl in `adapters/bus/ports.py`):
- `publish(msg: AgentMessage) -> None`
- `claim_next() -> AgentMessage | None` — atomically claim the next deliverable message (`SELECT … FOR UPDATE SKIP LOCKED`), respecting **one-in-flight-per-recipient** (a recipient with an unacked claimed message is skipped) so each per-agent queue drains **sequentially, FIFO**.
- `ack(msg) -> None` — mark done.

`AgentMessage`: `id`, `run_id`, `recipient` (the per-agent queue key `run:{run_id}:{role}`), `type`, `payload` (json), `status` (`pending/claimed/done`), `created_at/claimed_at`. Stored in a `bus_messages` table. This is the only channel between the API process and the worker, and the design that real containers poll in A4.

### 4.2 Worker (`interactors/worker/`, `make worker`)
A long-running loop whose core is a **testable** function:
`process_next(uow, bus, runtime) -> bool` — claim one message → dispatch to the agent handler for its `(recipient role, message type)` → the handler runs its stage via `runtime`, emits `RunEvent`s, advances the pipeline state machine, and publishes the next message (or pauses at a gate / finishes the run) → `ack`. Returns whether work was done (the loop sleeps a short interval when idle). Tests call `process_next` directly with a fake/real bus + `FakeAgentRuntime` — no live process required. `interactors/worker/main.py` is the thin `while True: process_next(...)` entrypoint.

### 4.3 Agents as message handlers (`domain/runs/orchestrator.py` + handlers)
- **lead** — orchestrates: on `start` kicks off PLAN; routes IMPLEMENT→engineer, VERIFY→QA; handles gate results, QA pass/fail (+ retry), and stage completion; finishes the run.
- **engineer** — runs IMPLEMENT via the runtime, reports back to the lead.
- **qa** — runs VERIFY via the runtime, reports pass/fail back to the lead.

Each handler is "receive message → run my stage via the `AgentRuntime` → publish a report to the lead." The lead is the only agent that advances the pipeline state machine. Handler selection is by `(role, message type)`.

### 4.4 `AgentRuntime` port (`domain/agent/runtime.py`)
`run_stage(role, stage, ctx) -> Iterator[AgentEvent]` terminating in a `StageResult` (`passed/failed` + a summary; token `usage` is `None` in A3). A3 ships **`FakeAgentRuntime`** only (`adapters/agent/runtime/fake.py`): scripted events per `(role, stage)` — e.g. PLAN emits a few "log" events then a `plan.md` summary; VERIFY can be scripted to fail-then-pass to exercise the retry path. A5 adds `ClaudeCodeRuntime` behind the same port.

## 5. Run domain model (`domain/runs/`, pure)

- **`Run`**: `id`, `owner_id`, `work_item_id`, `project_id`, `autonomy_level` (snapshot from the project at start), `status`, `current_stage`, `stages` (timeline), `verify_attempts`, `max_verify_loops` (default 3), `created_at/started_at/ended_at`.
- **`RunStatus`**: `queued · running · awaiting_gate · succeeded · failed · cancelled`.
- **`Stage`**: `PLAN · PROVISION · IMPLEMENT · VERIFY · PR · LEARN`. Each has a `StageState` (`pending/running/passed/failed/skipped/gated`), the `role` that ran it, and `started_at/ended_at`.
- **`RunEvent`** (append-only): monotonic `seq` per run, `run_id`, `stage`, `role`, `type` (`run_started · stage_started · log · stage_passed · stage_failed · gate_requested · gate_resolved · run_finished`), `payload` (json), `created_at`. Drives the SSE stream + Agent-Monitor.
- **`Gate`**: pending gate on a run — `kind` (`plan | merge`), the `stage` it guards, `created_at`; resolution (approve/reject) is an API action.

## 6. Stage state machine (`domain/runs/pipeline.py`) — the testable heart

Pure `next_step(run, stage_result) -> Step`, `Step ∈ {Advance(stage) | Gate(kind) | Retry(stage) | Finish(status)}`:
- `PLAN` passed → `Gate(plan)` if `gated_all`, else `Advance(PROVISION)`.
- `PROVISION` (stub) passed → `Advance(IMPLEMENT)`.
- `IMPLEMENT` passed → `Advance(VERIFY)`.
- `VERIFY` passed → `Gate(merge)` unless `full_auto` (then `Advance(PR)`); `VERIFY` failed → `Retry(IMPLEMENT)` while `verify_attempts < max_verify_loops`, else `Finish(failed)`.
- merge gate approved → `Advance(PR)`; `PR` (stub) → `Advance(LEARN)`; `LEARN` (stub) → `Finish(succeeded)`.

**Gates by autonomy** (`domain/runs/gates.py`): `gated_all` = plan + merge; `gated_merge` = merge only (plan auto-advances); `full_auto` = none. Gate **approve** resumes (lead publishes the next stage's message); gate **reject** → `Finish(cancelled)`.

## 7. Run ↔ work-item status coupling

Through the existing `domain/transitions.validate_transition` (all legal 5-state edges):
- run starts → work-item `→ in_progress`
- run reaches the merge gate (awaiting human) → `→ in_review`
- run succeeds → `→ done`
- run fails / is cancelled → `→ in_progress` (left for the user to retry; nothing silently advances to `done`)

The plan gate keeps the work-item `in_progress` (it's still being planned); only the merge gate moves it to `in_review`.

## 8. API surface (`interactors/api`, extends the UI contract)

- `POST /work-items/{id}/runs` → create `Run` (snapshot autonomy), publish `start` to the lead queue, transition the work-item → `RunOut` (201)
- `GET /runs?work_item=&project=&status=` → list (paginated, owner-scoped)
- `GET /runs/{id}` → `RunOut` with the stage timeline
- `GET /runs/{id}/events?after=<seq>` → `RunEvent[]` (cursor)
- `GET /runs/{id}/events/stream` → **SSE** (`text/event-stream`): tails `RunEvent`s after the last-sent `seq` on a short interval, yields new ones, closes with a terminal event when the run finishes
- `POST /runs/{id}/gate` → `{decision: "approve" | "reject"}` resolves the pending gate (publishes resume on approve; finishes `cancelled` on reject)

**Contract alignment (A2-4 pattern):** the backend emits the UI's camelCase `Run`/`AgentRun`/`Agent`/event shapes already defined (mocked) in `projects/ui/openapi/naaf-api.yaml` + `projects/ui/src/lib/api/schema.d.ts`, extending them where A3 needs fields. A run's "agents" = the roles that have processed/are processing its stages; the dashboard's "active agents" = roles with running stages across active runs. The UI's Runs/Agent-Monitor/inbox handlers move from `mockOnlyHandlers` to `liveHandlers` behind `VITE_LIVE_API`.

## 9. Persistence (`adapters/database/`)

New owner-scoped repos + ORM rows + one Alembic migration: `runs`, `run_events`, `bus_messages`. `RunEvent.seq` is monotonic per run (DB sequence or per-run counter). The bus table is indexed on `(recipient, status, created_at)` for `claim_next`. SQLite-in-memory for tests; Postgres migrated (note: `SKIP LOCKED` is Postgres-only — the bus impl degrades gracefully on SQLite for unit tests, or those tests target the claim logic via the repo).

## 10. Testing

- **Unit (pure domain):** `next_step` — every branch (plan gate / no gate / verify→merge gate / verify-fail→retry→fail / `full_auto` / `gated_merge`); gate logic; run/event/stage model; status mapping.
- **Adapter:** `MessageBus` Postgres impl (publish/claim/ack, one-in-flight-per-recipient, `SKIP LOCKED` concurrency); Run/RunEvent repos (owner-scoped).
- **Integration (the key test — "fakes + real bus"):** the full pipeline via `FakeAgentRuntime` driven through `process_next` — a `gated_all` run pauses at the plan gate, resumes on approve, retries on a scripted VERIFY fail, and reaches `succeeded`; the event stream, stage timeline, and work-item status are all correct. Also a `full_auto` run that completes without pausing, and a reject that cancels.
- **API:** start/get/list, events cursor, SSE yields events + closes on finish, gate approve/reject, camelCase contract shape, owner-scoping.
- 80% coverage gate + ruff/mypy clean.

## 11. Error handling & conventions (carried)

- Envelope `{success, data, error}` (+ `meta`) on every JSON response (SSE is the one streaming exception). Domain errors → HTTP via the existing handlers.
- Immutability (`model_copy`), owner-scoping (the UoW required-filter applies to runs/events/bus too), UUID-hex ids, TDD, `<type>: <description>` commits.
- Orchestration is **Local-First** (no Temporal): the worker drains per-agent queues sequentially; the pipeline's non-deterministic decisions live in `domain/`, the worker/bus adapters carry them out.

## 12. Implementation phasing (for the plan)

One spec; the plan phases along the substrate seams, each independently testable:
1. `Run`/`RunEvent`/`Gate`/`Stage` domain model + `next_step` state machine + gate logic + unit tests.
2. `MessageBus` port + Postgres impl + repos + Alembic migration (runs/run_events/bus_messages).
3. `AgentRuntime` port + `FakeAgentRuntime` (scripted, incl. fail-then-pass VERIFY).
4. Worker `process_next` + the lead/engineer/QA handlers + orchestration over the bus.
5. Run API (start/get/list/events/gate) + work-item status coupling + contract alignment.
6. SSE event stream.
7. Full fake-pipeline integration tests + `make worker` entrypoint + dev wiring (and the UI hybrid handlers flip for runs/agents/inbox).
