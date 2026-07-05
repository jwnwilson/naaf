# Stream agent output to the UI — design

**Date:** 2026-07-05
**Status:** Design (approved for planning)

## Problem

Every agent turn runs a **fully blocking** `claude -p` call. The worker
(`LlmChatResponder` / `LlmOrchestrator` for chat, `LlmAgentRuntime.run_stage`
for runs) calls `adapter.complete()`, which shells out to
`subprocess.run(claude -p --output-format json)` and only returns after the
entire agent loop finishes — then posts **one** final `Message`. The UI polls
`/threads/{id}/messages`, so the user sees ~60–90s of silence per turn, then a
wall of text. There is no visibility into what the agent is doing.

## Goal

Stream the agent's **full activity trace** into the UI as it happens — the
streamed text **plus** every tool call (`list_board`, `create_task`,
`propose_run`, …) and its result — for **both** chat threads (project lead +
work-item agents) and runs (plan → implement → verify pipeline). While a turn is
in flight and before the first output arrives, show a **`…` typing indicator**
in the chat.

## Decisions (locked during brainstorming)

1. **Output scope:** full activity trace — streamed text + tool calls + tool
   results. Doubles as a debug view.
2. **Surfaces:** chat **and** runs, sharing one transport.
3. **Persistence:** persist a **coarse** activity log (tool calls, tool results,
   text blocks) that is replayable on reload; the durable chat history stays in
   the `messages` table.
4. **Transport:** **Approach B — DB-only, poll-based SSE, no new infra.** The
   worker persists coarse events to a table; an SSE endpoint tails that table by
   polling (the exact pattern `/runs/{id}/events/stream` already uses). Text
   granularity is **per assistant turn/message** (appears every few seconds),
   not token-by-token. A Redis token-delta channel can be added later without
   changing the event model or the UI.
5. **Typing indicator:** reuse the existing `TypingIndicator` component; it is
   the "turn started, no content yet" state of the same event stream.

## Architecture & data flow

The feature turns one blocking call into a stream that **writes coarse events to
a table as it goes**, plus an SSE that tails that table.

```
Worker (Celery, single-concurrency)
  handler starts turn
    ├─ emit(status:"working")                          ─┐  each event →
    ├─ adapter.complete(request)  [event sink set]      │  AgentEventRepository
    │    claude -p --output-format stream-json --verbose│    .append(scope, kind, payload)
    │    Popen, read stdout line-by-line, parse NDJSON: │  → INSERT agent_events row
    │      • assistant text  → emit(text_block)         │
    │      • tool_use        → emit(tool_call)          │
    │      • tool_result     → emit(tool_result)        │
    │      • final result    → emit(final) ─────────────┘
    └─ post final Message row (unchanged chat history)

API (FastAPI, separate process)
  GET /threads/{id}/activity?after=<seq>   → replay persisted events
  GET /threads/{id}/activity/stream        → SSE: poll agent_events WHERE seq>after (~300ms)
  GET /runs/{id}/activity/stream           → same generator, scope="run:<id>"

UI
  open thread/run → SSE subscribe → replay + tail
    status:"working" (no content yet) → "…" typing indicator
    text_block / tool_call / tool_result → live ActivityFeed
    final → settle into final message; trace kept as expandable "activity"
```

Because the API and worker are separate processes, the SSE cannot read the
worker's memory — it polls the shared `agent_events` table, exactly as the
existing run-events SSE polls `run_events`. This is why Approach B needs no
Redis: the database *is* the cross-process channel.

## Data model — `agent_events` (new table)

| column | type | purpose |
|---|---|---|
| `id` | str(32) | uuid hex |
| `owner_id` | str | owner-scoping; required filter on every query (project convention) |
| `scope` | str(64) | `thread:<id>` or `run:<id>` — the stream key |
| `seq` | int | monotonic per-`scope` integer; drives `after` replay/resume |
| `kind` | str | `status` \| `text_block` \| `tool_call` \| `tool_result` \| `final` \| `error` |
| `payload` | JSON | text; or tool name + args; or result summary; or usage/error |
| `created_at` | timestamp | ordering / staleness |

Index on `(scope, seq)`. The `messages` table is unchanged and remains the
source of truth for durable chat history; `agent_events` is the live/replayable
**trace** beside it.

**Reconciliation rule:** the final assistant text lands in **both**
`agent_events` (`final`) and the existing `messages` row. The UI treats the
`messages` row as the completed turn and the activity trace as an expandable
detail on it — so there is no double-render.

## Components

### 1. Streaming runner — `adapters/agent/claude_cli/stream_runner.py` (new)

- `streaming_runner(argv, *, cwd, env, timeout, emit)` uses `subprocess.Popen`
  with `--output-format stream-json --verbose` (claude requires `--verbose` for
  stream-json under `-p`). Reads stdout line-by-line, `json.loads` each NDJSON
  line, maps claude event types → `emit(kind, payload)`, and accumulates the
  terminal `result`/`usage` to return the **same dict shape** `_default_runner`
  returns today.
- Timeout, `FileNotFoundError`, non-JSON, and non-zero-exit handling mirror the
  current runner and surface a terminal `error` event.
- `_default_runner` stays as the non-streaming default; the streaming runner is
  used only when a sink is present. Both keep the injectable-`runner` test seam.

### 2. Adapter — `claude_cli/adapter.py` (minimal change)

- Add `set_event_sink(emit)` — mirrors the existing `set_cwd` per-call setter
  (safe under single-concurrency). When a sink is set, `complete()` uses the
  streaming runner and forwards events. The `LLMAdapter.complete(request)` port
  signature is **unchanged**; non-claude adapters ignore sinks.

### 3. Domain + persistence

- `domain/agent/events.py` — pure `AgentEvent` model, a
  `stream_scope(thread_id | run_id) -> str` helper, and the `kind` literal set.
  No I/O.
- `AgentEventRepository` (`adapters/database/repositories.py`):
  `append(scope, kind, payload) -> AgentEvent` (computes next per-scope `seq`),
  `list_after(scope, after_seq, limit) -> list[AgentEvent]`. Wired into
  `uow.py` and `ports.py` alongside the other repositories.
- ORM row `AgentEventRow` in `orm.py`; Alembic migration `0014_agent_events`
  (down_revision `0013_widen_message_thread_id`) using **batch mode**
  (SQLite-safe) with the `(scope, seq)` index.

### 4. Worker sink wiring — `interactors/worker/handlers.py`

- `build_event_sink(ctx, scope) -> emit` returns a closure that calls
  `ctx.agent_events.append(scope, kind, payload)`.
- Each handler emits `status:"working"` up front, calls
  `adapter.set_event_sink(emit)` before `respond()` / `run_stage()`, and emits
  `final` / `error` at the end. `handle_project_chat` + `handle_chat` use
  `thread:<id>`; the run stage runner uses `run:<id>`. The final `Message` post
  is unchanged.
- `HandlerContext` gains an `agent_events` repository (built in `ctx_factory`,
  owner-scoped like the others).

### 5. API — `routes/activity.py` (new) + one line in the runs router

- `GET /threads/{id}/activity?after=` → list persisted events (replay).
- `GET /threads/{id}/activity/stream` and `GET /runs/{id}/activity/stream` →
  `EventSourceResponse` backed by a shared `stream_agent_events(scope, after)`
  generator that reuses the existing runs-SSE poll loop (poll `list_after`
  ~300ms, honor `Last-Event-ID` / `after`, heartbeat). No duplication.
- Fully additive — no existing endpoint or the `messages` flow changes.

### 6. UI

- **`useAgentActivity(scope)`** — opens the activity SSE (`EventSource`), replays
  via `?after=`, and reduces the event stream into
  `{ status, textBlocks[], toolCalls[], isWorking, error }`, tracking the last
  `seq` for clean reconnect. One hook serves chat and the run monitor. Adds an
  envelope-typed `ActivityEvent` to the API client + a React Query key for the
  replay fetch.
- **`ActivityFeed`** — renders the in-flight trace: streamed `text_block`s and
  each `tool_call` / `tool_result` as a compact line (e.g. `🔧 create_task → ok`).
  This is the "see all the output" view.
- **`TypingIndicator`** (exists) — shown as an agent bubble the moment
  `status:"working"` arrives and before the first `text_block`, and again between
  turns while a tool runs with no text. This is the **`…` while waiting**.
- **Chat thread:** in-flight turn shows `TypingIndicator` → streaming
  `ActivityFeed`; when the turn's `Message` row lands (existing messages query)
  the bubble **settles into the final message**, trace available as a collapsible
  "activity" section. The `messages` row is the completion signal.
- **Run monitor (Detail screen):** the active stage renders the same
  `ActivityFeed`, replacing the current wait-for-stage-event gap.

## Error handling

- **claude non-zero exit / non-JSON / crash:** streaming runner catches it (as
  `_default_runner` does today), returns `is_error` so the handler still posts a
  fallback `Message`, and emits a terminal `error` event so the UI clears the
  "…" and shows the failure. No hang.
- **Timeout:** `Popen` wall-clock guard (same `timeout_s`); on expiry, kill the
  process, emit `error`, post the timeout message.
- **Malformed NDJSON line:** skipped defensively (logged); the stream continues.
- **Worker dies mid-turn (no `final`):** the `messages` row never appears, so the
  UI keeps showing the trace; on SSE reconnect the client sees no new events and
  falls back to the "no active turn" idle state once the bus message is gone. A
  `status:"working"` event older than the claude timeout is treated as stale by
  the client.
- **SSE drop:** client reconnects with `after=<last seq>` and resumes — no gaps,
  no dupes (monotonic `seq`).
- **DB write pressure:** coarse events only (per-turn text blocks + tool calls),
  not tokens — bounded volume, consistent with Approach B.

## Testing (TDD)

- **Streaming runner:** scripted stream-json stdout fixture through an injected
  runner → assert ordered `emit` calls
  (`status`→`text_block`→`tool_call`→`tool_result`→`final`) and that assembled
  `result`/`usage` match the old blocking contract. Include bad-line and
  error-exit fixtures.
- **Repository:** `append` yields monotonic per-scope `seq`; `list_after`
  filters/orders; owner-scoping enforced.
- **Handler:** fake adapter drives the sink → assert the expected `agent_events`
  rows persist for a scripted turn and the final `Message` still posts.
- **API:** `/activity` replay returns events after `seq`; `/activity/stream`
  yields new events (reuse the existing SSE test pattern); `Last-Event-ID`
  resume works.
- **UI (vitest):** `useAgentActivity` reduces a mock SSE into
  typing-indicator → trace → settled-message states; `ActivityFeed` renders text
  blocks + tool lines; reconnect replays without dupes. Mock handlers extended so
  the UI runs fully mocked.
- **Gates:** `make coverage` (80%) + `make lint`; UI `vitest`.

## Suggested build order (phases)

1. **Backend foundation:** `AgentEvent` domain model + `agent_events` table +
   migration + `AgentEventRepository` + streaming runner (with tests).
2. **Wiring:** worker sink (`build_event_sink`, `HandlerContext.agent_events`,
   emit calls in chat + run handlers) + API `routes/activity.py` and the runs
   router line.
3. **UI:** `useAgentActivity` + `ActivityFeed` + `TypingIndicator` in the chat
   thread; then the run monitor.

## Out of scope (deferred)

- Token-by-token ("stream fine") deltas via a Redis pub/sub channel — the event
  model and UI are designed so this can be added later without breaking changes.
- Cost/usage rendering from `agent_events` payloads (A5d territory).
- Persisting or replaying token-level animation (Approach B is per-turn).
