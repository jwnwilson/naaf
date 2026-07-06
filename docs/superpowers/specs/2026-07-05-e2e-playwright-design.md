# Playwright end-to-end test — design

**Date:** 2026-07-05
**Status:** Design (approved for planning)

## Problem

NAAF has unit/component tests (pytest, vitest) but **no browser end-to-end test** that
exercises the full stack: UI → live API → worker → agent → streamed activity back to the
UI. The just-shipped streaming feature (agent activity → `agent_events` → SSE →
`ActivityFeed`) has no automated test that proves the real UI shows streamed output during
a real run. We want an e2e that covers the core journey:

1. Chatting to the lead
2. The lead creating a task
3. Triggering a run with multiple agents (stages/roles)
4. Seeing that agent output streamed on the UI

## Goal

A reliable, repeatable Playwright suite that drives the **real full stack** through a browser
and asserts the four capabilities above — fast and deterministic enough for CI, plus an
opt-in real-`claude` smoke variant for occasional true end-to-end validation.

## Decisions (locked during brainstorming)

1. **Test target:** **Hybrid.** A deterministic scripted suite is the primary, CI-safe path;
   plus one opt-in real-`claude` smoke test (tagged, off by default) reusing the same flow.
2. **Determinism mechanism:** **Approach A — a scripted LLM adapter.** Swap only the model.
   The real `LlmOrchestrator` / `LlmChatResponder` / `LlmAgentRuntime` (with the real tool
   loop + `set_event_sink` → `agent_events` → SSE → `ActivityFeed`) run unchanged; only
   `LLMAdapter.complete` is scripted. The e2e therefore validates the genuine end-to-end path
   — it would catch a regression like "the run-stage sink wasn't wired."
3. **Full stack, real streaming:** the test runs against the live API + worker + Postgres +
   UI (live-API mode) — not the MSW-mocked UI — because the point is to see the real
   SSE → UI stream.

## Architecture & harness

```
Playwright (chromium, headless)  ──drives──▶  UI :5173 (live-API mode)
                                                   │ /api → :8000
        boots + waits on ▼                    real API :8000 ──┐
  make e2e / globalSetup:                                      ├── same Postgres (docker)
   • docker Postgres  • migrate + seed                 worker (Celery) ──┘
   • API + worker + UI, env:                                   │
     naaf_llm_provider=scripted                        LlmOrchestrator / LlmAgentRuntime
     naaf_agent_runtime=claude_code  (non-fake)          │  (real tool loop + set_event_sink)
     naaf_secret_key=<test key>                     ScriptedLLMAdapter  ← the ONLY fake
```

Setting `naaf_llm_provider=scripted` + a non-`fake` `agent_runtime` routes **chat and runs**
through the production `LlmOrchestrator` / `LlmChatResponder` / `LlmAgentRuntime`, including
the full `set_event_sink` → per-event-commit → SSE → `ActivityFeed` pipeline. Postgres is the
only Docker dependency (already used by `make dev`).

## The scripted adapter

`ScriptedLLMAdapter` implements the real `LLMAdapter` port (`complete(request) -> LLMResponse`)
+ `set_event_sink(emit)`. It is context-aware — it decides what to return by inspecting the
request, so it works inside the real tool loop with no special orchestration. It branches on
which tools the request carries:

1. **Lead planning** (request carries the orchestration tool specs — `list_board`,
   `create_epic`, `create_feature`, `create_task`, `propose_run`): returns a scripted
   sequence of tool-calls, choosing the next step from how many tool-results are already in
   the message history: `list_board` → `create_epic` → `create_feature` →
   `create_task("E2E streaming task")` → `propose_run` → then a final text summary (no
   tool-calls, ending the loop). The real `run_tool_loop` executes each against the real
   `CtxOrchestrationTools`, so a real epic/feature/task land on the board. While looping, if a
   sink is attached it emits a couple of `text_block` / `tool_call` activity events so the
   **chat** `ActivityFeed` streams.
2. **Run stage** (request carries the `report` tool spec — `LlmAgentRuntime.run_stage`): if a
   sink is attached, emits a fixed sequence — `text_block("Scanning the repository…")` →
   `tool_call("edit_file")` → `tool_result("ok")` → `text_block("Changes applied.")` — then
   returns a `report` tool-call with `passed=true` and a stage summary. Each run stage
   (plan/implement/verify) streams a known trace into the **run monitor**.
3. **Plain agent chat** (neither toolset — a work-item role reply): emits one or two
   `text_block`s and returns a short scripted reply.

**Determinism:** all scripted strings are module-level constants (the e2e asserts on them);
no time/randomness. The same run always produces the same `agent_events` sequence.

**Wiring:** add a `scripted` branch to `build_llm_adapter` (`adapters/agent/factory.py`)
returning `ScriptedLLMAdapter`. With `agent_runtime != fake` and `llm_provider = scripted`,
`build_agent_deps` falls through to the generic LLM path, building
`LlmChatResponder`/`LlmOrchestrator`/`LlmAgentRuntime` on the scripted adapter (the
`claude_cli` MCP path is not taken; no MCP needed).

## Test flow & assertions

One primary journey spec (`e2e/streaming-journey.spec.ts`):

| # | Step (Playwright drives the UI) | Assertion |
|---|---|---|
| 1 | Navigate to the board; create a project (or open the seeded one) | project visible in the sidebar |
| 2 | Open the project chat, type "Build a notes feature", send | user message appears in the thread |
| 3 | Chat → lead streams | chat `ActivityFeed` shows the `…` typing indicator, then the scripted `text_block` / `tool_call` trace |
| 4 | Lead creates a task | a work item titled **"E2E streaming task"** appears on the board (`expect.poll` until the worker commits it) |
| 5 | Open the task, click **Start run** | run enters `running`; run monitor renders |
| 6 | Run streams multi-stage output | run monitor `ActivityFeed` shows the scripted stage trace — `"Scanning the repository…"` → `🔧 edit_file` → `"Changes applied."` — across plan→implement→verify (multiple roles) |
| 7 | Run reaches a terminal/gate state | stage list shows stages passed; run status advances |

**Assertion style:** web-first assertions + `expect.poll(...)` for the async worker→SSE→UI
hops — **no fixed `sleep`s**. Scripted strings live in a shared `e2e/fixtures/scripted.ts`
mirroring the backend constants, so a drift between them fails loudly.

**Isolation:** the suite runs under dev auth (`dev-user`, no real login). `globalSetup`
provisions a **clean e2e database** (a dedicated `naaf_db_url`, migrated + seeded fresh) so
the journey starts from a known state and is re-runnable — no production reset endpoint is
added. Because the suite is a single journey test, no per-test reset is needed; if later specs
interfere, a guarded truncate in support code is the follow-up (never run against a non-e2e
`naaf_db_url`).

**Scope discipline (YAGNI):** one comprehensive journey test covering the four capabilities —
the streamed steps are only meaningful in sequence — not a sprawl of micro-tests. The
real-`claude` smoke reuses this exact spec under a `@real` tag with loosened text assertions
("a task was created" + "some non-empty streamed text appeared").

## Running it

**Local — `make e2e`:**
1. `docker compose up -d postgres`, `make db-upgrade`, seed.
2. Boot API + worker + UI with `naaf_llm_provider=scripted naaf_agent_runtime=claude_code
   naaf_secret_key=<test>` (a headless variant of the `make dev` orchestration).
3. `pnpm --dir projects/ui exec playwright test`.
4. Tear down on exit.

Playwright `globalSetup` waits on `GET :8000/health` + the Vite server before tests;
`globalTeardown` stops the stack.

**CI — `.github/workflows/e2e.yml`:** Postgres service container, `uv sync`, `pnpm install`,
`playwright install --with-deps chromium`, boot the scripted stack, run the suite, and on
failure upload the Playwright **trace + screenshots + video** as artifacts. The `@real` smoke
test is excluded in CI; it's a manual `workflow_dispatch` (or local `NAAF_E2E_REAL=1 make
e2e-real` with `naaf_llm_provider=claude_cli` + a real token).

## File layout

```
projects/server/src/adapters/agent/scripted/adapter.py   # ScriptedLLMAdapter
projects/server/src/adapters/agent/factory.py            # +scripted branch in build_llm_adapter
projects/ui/playwright.config.ts                         # chromium, baseURL, global setup/teardown, trace-on-retry
projects/ui/e2e/streaming-journey.spec.ts                # the journey
projects/ui/e2e/fixtures/scripted.ts                     # shared scripted constants (mirror backend)
projects/ui/e2e/support/{globalSetup,globalTeardown,reset}.ts
Makefile                                                 # e2e, e2e-real targets
.github/workflows/e2e.yml
```

## Flakiness & error handling

- **No fixed sleeps** — `expect.poll` / web-first assertions with generous timeouts for the
  worker→bus→SSE hops; `retries: 1` in CI; `trace: 'on-first-retry'`.
- Scripted determinism removes the biggest flake source (variable model output); the single
  serial worker processes the journey's run predictably.
- `globalSetup` fails fast with a clear message if the stack isn't healthy within N seconds
  (dumps API/worker logs).
- The reset step is idempotent and guarded to the e2e database (never runs against a
  non-test `naaf_db_url`).
- The `@real` variant is fully **skipped** (not failed) when its token env is absent.

## Testing the harness itself (TDD where it applies)

The `ScriptedLLMAdapter` is pure Python and unit-tested with pytest (TDD): given a request
with orchestration tools, it returns the expected next tool-call for each step; given a
`report`-tool request with a sink, it emits the fixed event sequence and returns
`passed=true`. The Playwright spec is the integration surface and is validated by running the
suite green against the scripted stack.

## Out of scope (deferred)

- Visual-regression / screenshot-diff testing.
- Gate approve/reject and PR-stage flows (the journey stops at streamed run output; gates can
  be a follow-up spec).
- Multiple parallel projects/runs; cross-browser (chromium only for now).
- Load/perf testing of the SSE.
