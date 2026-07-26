# naaf — Project History & Status

> **Read this first.** A concise record of what has been built, what is designed-only,
> and what comes next.

## What naaf is

A self-hosted platform for running **virtual dev teams** — role-based AI agents (lead,
architect, backend/frontend engineers, QA, devops) — against real repositories, driven from
a visual kanban board (projects → epics → features → tasks). Agents work in sandboxed Docker
containers with centrally managed secrets, permissions, skills, MCP servers, and models;
produce reviewable PRs; and update persistent memory as they work.

- Master design: [specs/2026-06-12-naaf-design.md](specs/2026-06-12-naaf-design.md)
- Architecture & patterns: [architecture.md](architecture.md)
- ADRs: [adr/](adr/)

## Current state (2026-07-05)

The **local single-user product is end-to-end functional**: you can plan work on the board, chat with
a lead to create the epic→feature→task tree, start real agent runs that clone the repo and open PRs,
watch them live, and manage credentials — all with the dashboard reflecting real activity. What ships
today:

- **Control plane (A1) ✓** — Project + unified WorkItem (epic/feature/task) hierarchy + status
  machine; owner-scoped Repository/UnitOfWork; envelope-aware CrudRouter; config Team/AgentDefinition.
- **UI (A2) ✓** — all 7 screens, live-API for projects/work-items/teams/agent-definitions/runs/
  threads/secrets/attachments/agents (MSW mocks only for `/dashboard/metrics` + `/budget`).
- **Run pipeline (A3) ✓** — `Run` entity + status machine; **local pub/sub** orchestration; the worker
  drives `PROVISION → PLAN → IMPLEMENT → VERIFY → PR → LEARN` with human gates, `RunEvent`s, and SSE.
- **Agent runtime (A5) ✓** — LLM-agnostic `LlmAgentRuntime` reaching the model only via one
  `LLMAdapter` port; three adapters: Claude SDK, LiteLLM, and **Claude CLI / subscription** (`claude -p`,
  no API key) + a naaf MCP server so the lead drives the board itself.
- **Containerized E2E worker (A4 slice 1) ✓** — role-configured Docker worker runs the full run and
  opens a PR via `gh`.
- **Conversational substrate (A6 slices) ✓** — work-item threads, run narration into threads, gates as
  answerable messages, `@mention` agent↔agent dispatch, the conversational lead, and D3 thread-tab
  parity (agent identity/model/status).
- **Secrets management (C slice) ✓** — Settings → Secrets, Fernet-encrypted at rest, per-owner run
  injection.
- **Dashboard ✓ (fully live)** — live-agents panel + ACTIVE-AGENTS count, board ribbon, TokenChart,
  ActivityFeed, and now the metric cards + budget (real per-model spend) all backed by real data;
  only `/projects/:id/board` is still mocked. The board polls for live refresh.
- **Work-item file uploads ✓** — `storage` lib (Local default / S3), attachments API, and
  materialization into the agent workspace.
- **Live agent output streaming ✓** — the worker streams a coarse activity trace (text / tool calls /
  results) into chat + runs via `agent_events` + poll-based SSE, with a typing indicator.

See the dated log below for the detail on each, and **Outstanding** at the bottom for what's left.

## Status (2026-07-07)

**Async DB layer (`libs/db`) + SSE event-loop-freeze fix — built.** The activity and run-events SSE
streams were blocking the API's single event loop under load (each poll iteration ran a **sync**
SQLAlchemy query inside an `async def` endpoint with no `run_in_executor`, so a long-poll starved
every other request). `naaf_db` gained an **async sibling** of its sync engine/repository/UnitOfWork
(`build_async_engine`, `AsyncSqlRepository`, `AsyncUnitOfWorkBase`, minimal `AsyncAgentEventRepository`
+ `AsyncRunEventRepository`) sharing the same pure query-builders (`_query.py`) as the sync path — no
duplicated filter/order/paginate logic. The FastAPI app now carries an async engine on `app.state`
(disposed in the lifespan shutdown) via `get_async_uow`, and **both SSE endpoints** (activity +
run-events) were converted to await the async UoW, unblocking the event loop while streams are open.
Sync endpoints and the worker are unchanged (still the sync `SqlUnitOfWork`). Tested with an
`aiosqlite` in-memory mirror of the sync repository test suite (create/read/read_multi/update/delete/
delete_where) plus the existing Postgres integration coverage; `naaf_db` is now included in the
coverage gate (`[tool.coverage.run].source`).

## Status (2026-07-05)

**A5d — real per-model pricing + live spend/budget (display slice) — built.** The flat placeholder
cost is gone: a `naaf_model_prices` settings dict (keyed by model alias, `{input, output}` USD-per-1k,
defaults for opus/sonnet/haiku) + a pure `domain/pricing.py` `price_stage(model, in, out, prices)`
(output priced ~5× input) give real cost. The runtime stops collapsing tokens — each `StageResult`
carries `input_tokens`/`output_tokens`/`model` — and `_finish_stage` prices the stage and accumulates
a **persisted `Run.cost`** (float column, migration `0015`) alongside `token_usage`, so `RunOut.cost`
is real (captured at run-time) and the flat `COST_PER_1K_TOKENS` is deleted. Two new owner-scoped
routes light up the **last mock-only dashboard endpoints**: `GET /dashboard/metrics` (Σ cost / Σ
tokens / project+work-item counts / active-run count) and `GET /budget` (used = Σ cost, limit =
`naaf_budget_limit_usd`, default $100). On the UI, `useDashboard`/`useBudget` poll every 10s, both
handlers moved MSW mock-only → live, and the MetricCards **and the Sidebar budget footer** render USD
— **only `/projects/:id/board` remains mocked now**. Note: Claude-CLI **subscription** cost is
*notional* (flat-rate sub), shown as an estimate. **Deferred to A5d-2 (enforcement):** a settable
per-owner `Budget` entity + set-budget UI, the worker halting runs at the cap, monthly reset/periods,
and a per-model spend breakdown. Design:
[superpowers/specs/2026-07-05-a5d-pricing-usage-design.md](superpowers/specs/2026-07-05-a5d-pricing-usage-design.md);
plan: [superpowers/plans/2026-07-05-a5d-pricing-usage.md](superpowers/plans/2026-07-05-a5d-pricing-usage.md).

**Live agent output streaming (`stream-agent-output`) — built.** Agent turns no longer run as one
opaque blocking call — the worker now **streams a coarse activity trace** (text blocks, tool calls,
tool results, status/final/error) into the UI as it happens, for **both chat threads and runs**. A
new **`agent_events`** table (migration `0014`) + `AgentEventRepository` (`append`/`list_after`,
per-`scope` `seq`) is the cross-process channel; a **streaming runner** (`claude_cli/stream_runner.py`,
`claude -p --output-format stream-json`) parses NDJSON and forwards events through an adapter event
sink, while the durable chat `messages` history stays the source of truth. The API adds
`GET /threads/{id}/activity` (replay) + `/threads/{id}/activity/stream` and `/runs/{id}/activity/stream`
(poll-based SSE, same pattern as the run-events stream — no new infra). The UI reduces the stream into
a live trace with the existing `TypingIndicator` for the "working, no output yet" state. Deferred:
token-by-token deltas via Redis (the event model is designed to add them without breaking changes).
PR #56.

**Dashboard TokenChart + ActivityFeed — built.** The last two mocked dashboard widgets are now
live, backed by the existing `RunEvent` stream (read-only aggregation — no new table or migration).
Two pure domain aggregators (`domain/dashboard.py`): `build_token_series` buckets per-stage token
deltas (`RunEvent.payload["tokens"]` on `stage_passed`/`stage_failed`) into a **7-day zero-filled
series**; `to_activity_event` maps a `RunEvent` to an activity row (`log` and null-timestamp events
dropped). A new `routes/dashboard.py` serves owner-scoped **`GET /dashboard/token-usage`** (reads
run_events since a 7-day cutoff, aggregates) and **`GET /activity`** (recent cross-run events ordered
by `-global_seq`, mapped, capped at 20). On the UI, `useTokenUsage`/`useActivity` **poll every 10s**
(paused when the tab is hidden) and the two endpoints moved from MSW mock-only to live-backed; the
**TokenChart/ActivityFeed components are unchanged** (contract shapes match). **Follow-up:** now that
`stream-agent-output` (PR #56) has landed its `agent_events` trace, the dashboard `/activity` feed
*could* be re-pointed at that richer source behind its unchanged contract — an available (unbuilt)
swap, not a dependency. Still mocked: `/dashboard/metrics` other cards + real per-model pricing (A5d).
Design:
[superpowers/specs/2026-07-05-dashboard-token-activity-design.md](superpowers/specs/2026-07-05-dashboard-token-activity-design.md);
plan: [superpowers/plans/2026-07-05-dashboard-token-activity.md](superpowers/plans/2026-07-05-dashboard-token-activity.md).

## Status (2026-07-04)

**Live agents on the dashboard — built.** The dashboard's "running agents" panel and the
"ACTIVE AGENTS" metric are now real, replacing the mock. A pure domain aggregator
(`domain/live_agents.py` `build_live_agents`) joins the enabled `AgentDefinition` roster with
active runs (`status ∈ {running, awaiting_gate}`) into **one row per team role**, marking a role
**running** when a run's current stage maps to it (`lead→lead`, `engineer→backend`, `qa→qa`;
most-recently-started run wins on same-role ties; progress = passed stages / 6; fixed role order;
architect/frontend/devops stay idle since the pipeline never dispatches them). A new owner-scoped
**`GET /agents`** endpoint (`AgentOut` contract) serves the rows — read-only aggregation, **no new
persistence or migration**. On the UI, `useAgents` was reshaped to the role rows and **polls every
5s** (paused when the tab is hidden, like the board); the dashboard **RunningAgentsPanel**, the board
**LiveAgentsRibbon**, and the **ACTIVE AGENTS** count all render live; `/agents` moved from MSW
mock-only to live-backed with reshaped fixtures so mock mode still renders. **Deferred (per spec):**
global/cross-run SSE (polling chosen), TokenChart + ActivityFeed + the other metric cards stay
mocked, agent pause/assign actions (no backend action), and a persisted agent-runtime entity (the
roster + active runs are the source of truth). Design:
[superpowers/specs/2026-07-04-live-agents-dashboard-design.md](superpowers/specs/2026-07-04-live-agents-dashboard-design.md);
plan: [superpowers/plans/2026-07-04-live-agents-dashboard.md](superpowers/plans/2026-07-04-live-agents-dashboard.md).

**Thread tab — D3 design parity (agent identity, model & status) — built.** The work-item Detail
**Thread** tab now surfaces the agent details the hi-fi design (frame **D3**) calls for, closing the
gap where messages had no author identity and the rail listed raw role strings (`lead`/`backend`).
Backend: a new **`ThreadParticipant`** projection enriches each distinct sender with a display name
(role→label map), the **latest model** seen for that role, and **running/idle** status derived from a
run's currently-running stage roles (`_active_roles` reads `StageState.role`, which the pipeline
populates at `handlers.py`). It's exposed as **`participantDetails` on `ThreadDetailOut` only** — the
existing `Thread.participants: string[]` is untouched, so the sidebar chat and inbox are unaffected
(zero blast radius). OpenAPI + FE `schema.d.ts` regenerated. Frontend: `MessageItem` gained an author
header (name + timestamp + model badge), lead (violet) vs subagent (muted `subagent` Avatar variant)
avatars, and `@mention` + inline-code highlighting; `ThreadRail` renders **PARTICIPANTS** (name +
Running/Idle dot), **THREAD INFO** (messages/started/task), and styled **FILES WRITTEN** cards;
`Thread` adds day dividers + a typing indicator (gated on an active run, reusing `ui/TypingIndicator`).
New tested helpers `agentIdentity`/`renderContent`/`groupByDay`; the mock `GET /threads/{id}` now
returns enriched detail for the offline UI. Verified with unit/API tests (server 90.9% coverage) and a
headless-browser screenshot of the rendered tab. Reference: `docs/design/NAAF Hi-Fi.dc.html` (D3);
PR #51.

**Claude Code CLI runtime (subscription-backed agents) — built.** A new
`naaf_llm_provider=claude_cli` mode runs all agent LLM work through headless Claude Code
(`claude -p`, authed by the user's **subscription** — no Anthropic API key), fulfilling the
roadmap's "A5 Claude Code runtime adapter." It's a **single new `LLMAdapter`**
(`ClaudeCliLLMAdapter`): `complete()` shells out to `claude -p --output-format json
--permission-mode bypassPermissions` and captures the JSON into an `LLMResponse` (content + usage)
— so the **existing** `LlmAgentRuntime`, `LlmChatResponder`, and `LlmOrchestrator` are reused
unchanged. On run stages (detected by the `report` tool spec) it maps Claude's `VERDICT: PASS|FAIL`
into a synthesized `report` tool-call so VERIFY semantics hold; the runtime's `workspace_factory`
points the adapter at each stage's workspace. For the lead-chat to reach naaf's own domain, a
**naaf MCP server** (`interactors/mcp/`, FastMCP, 10 owner-scoped tools over existing code —
create/update/list/propose/start/transition + reads) is attached via `--mcp-config`, so Claude Code
creates the epic→feature→task tree and proposes runs itself. Per-owner deps built in `ctx_factory`
(MCP scoped by owner via env; project resolved by Claude via `list_projects`); `github_token`
injected for `gh`; `mcp` + `naaf_claude_bin`/`naaf_claude_timeout_s` added. The API-key adapters
remain. Design:
[superpowers/specs/2026-07-04-claude-cli-runtime-design.md](superpowers/specs/2026-07-04-claude-cli-runtime-design.md).

**Work-item file uploads — built.** You can attach text/image files to any work item and agents
read them during a run. A new app-agnostic **`storage` workspace lib** (`libs/storage/`) provides a
bytes-oriented `Storage` port with a default **`LocalStorage`** adapter (rooted at `~/.naaf`) and an
**`S3Storage`** adapter (lazy `boto3`, `s3` extra — shipped as code, not the active backend). Keys
follow one convention everywhere — `work-item/<uuid>/<filename>` — identical for local disk and S3,
so cloud drops in later without touching callers. Server side: an **`attachments`** table (entity +
owner-scoped repository + migration `0011`) holds metadata while bytes live in storage; **multipart
`POST`/`GET`/`DELETE /work-items/{id}/attachments`** endpoints (envelope + owner-scoped, load the
work item first) validate size (413, 10 MB cap), content-type allowlist (415), and duplicate
filename (409 unless `overwrite=true`); downloads force `Content-Disposition: attachment` with an
RFC-6266-encoded filename (no in-origin SVG render). `WorkItemOut.attachments` is now populated.
Agent access: at **provision** the worker materializes a work item's attachments into
`<workspace>/.naaf/attachments/` (via the `Storage` port, so S3 works later) and `stage_instruction`
lists them; the attachments root is bind-mounted into the worker container. UI: a Detail-screen
**Attachments panel** (list · upload with an overwrite-confirm guard · delete-confirm) wired to three
React Query hooks + an `apiUpload` multipart helper, with MSW mocks for offline demo. Deferred (per
spec): MinIO/compose S3 service, S3 prefix sync-down at provision, image vision, PDFs/binaries.
Design: [superpowers/specs/2026-07-04-work-item-file-uploads-design.md](superpowers/specs/2026-07-04-work-item-file-uploads-design.md);
plan: [superpowers/plans/2026-07-04-work-item-file-uploads.md](superpowers/plans/2026-07-04-work-item-file-uploads.md).

**Secrets management — built.** Agent credentials (Anthropic key + GitHub token) are now managed
in a **Settings → Secrets** page and injected into agent runs, replacing the global-env-only model
(first step of the master spec's `Secret` entity + management plane). Owner-scoped `Secret` store,
**Fernet-encrypted at rest** (`naaf_secret_key`; writes fail closed if unset), **write-only** API
(`GET/PUT/DELETE /secrets` returns only `{name, isSet, hint}` — the value never leaves the server;
`hint` is the last 4 chars). Injection is resolved **per owner** in `ctx_factory`: a stored
Anthropic key builds a per-owner LLM adapter/runtime (`build_agent_deps`) and a stored GitHub token
is baked into the run runtime's `LocalWorkspace` subprocess env (`GH_TOKEN`) for the agent's
`git`/`gh` — both **falling back to the env vars** when unset, so `make dev` with env still works
(`SecretResolver`). UI: a masked Secrets form (`SecretsPanel`) showing **Set ••••1234 / Not set**
with Save/Clear. Migration `0011_secrets`; `cryptography` added. **Deferred (spec end-state):**
credential-injecting egress proxy / placeholders, GitHub App per-run tokens, per-project secrets,
audit log. Design:
[superpowers/specs/2026-07-04-secrets-management-design.md](superpowers/specs/2026-07-04-secrets-management-design.md).

**Live board refresh — built.** The board now **polls while mounted** (`useBoard` gained a
`refetchInterval`, `BOARD_POLL_MS=5000`; paused when the tab is hidden), so work items the agents
create/move server-side — the conversational lead's new epics/tasks and run-driven status changes —
appear **without any user interaction**. Complements D's on-send/answer board invalidation (which
only covered synchronous/mock creates). A board SSE stream would be lower-latency but is deferred —
polling is the right cost/complexity trade for a local single-user tool.

**Conversational lead (D) — built.** You can now plan a project by chatting with a **lead agent**
in a new **project-level thread** (`project:<id>` — a namespaced thread id, no schema change). The
lead has a **tool surface**: a `LeadOrchestrator` (LLM-backed `LlmOrchestrator`, or the
deterministic `EchoOrchestrator` offline/tests) drives domain-action tools via a shared
`run_tool_loop` — `list_board`, `create_work_item` (hierarchy-validated), `update_work_item`, and
`propose_run`. Tools execute through a `CtxOrchestrationTools` adapter over the owner-scoped worker
context, so created epics/features/tasks and the run proposal appear on the board + in the thread.
Autonomy is **auto-create, propose-to-run**: work items are created directly, but development is a
**`run_proposal` question** the human approves in-thread — approval runs the shared `start_run`
sequence per task (extracted from the runs route). `handle_chat` gained a project branch; the
orchestrator is wired through `factory`/`subscription_runner`/`celery`. On the UI, the right-rail
**chat becomes "Chat with lead"** and targets the project thread when a project is selected on the
board (reusing the shared `<Thread>`), with a mock orchestrator simulating the flow offline.
**Deviation from the spec:** the stage runtime still keeps its own loop — `run_tool_loop` is shared
by the orchestrator but unifying `LlmAgentRuntime.run_stage` onto it is a deferred, lower-risk
cleanup. Completes the **B → A+C → D** dogfooding sequence. Design:
[superpowers/specs/2026-07-03-conversational-lead-design.md](superpowers/specs/2026-07-03-conversational-lead-design.md).

## Status (2026-07-03)

**Dogfood setup + UI run controls (A+C) — built.** NAAF can now be driven end-to-end on its own
repo from the UI. **Start run** control on the Detail screen (header + Agent-tab empty-state CTA)
starts a run via `POST /work-items/{id}/runs` — shown only for **Task/Feature**, disabled (with a
tooltip) unless the item is startable and has no active run, gated behind a confirm dialog, with
409s surfaced inline (`useStartRun` hook + `StartRunButton`). The run's opened PR is now
**first-class**: a nullable `pr_url` column persists on `Run` (migration `0010`), `_capture_pr_url`
stamps it (preserved through Finish via the post-PR re-read), `RunOut.prUrl` exposes it, and the
run monitor renders a **View PR** link. A [dogfooding runbook](../dogfooding.md) documents running
against `https://github.com/jwnwilson/naaf` with `make dev NAAF_AGENT_RUNTIME=claude_code` +
`naaf_anthropic_api_key`/`GH_TOKEN`, with a validation checklist. Mock mode gained a start-run
handler + `addRun` and a succeeded seed run with a `prUrl` so the whole flow is demoable offline.
Second of the **B → A+C → D** sequence. Design:
[superpowers/specs/2026-07-03-dogfood-run-controls-design.md](superpowers/specs/2026-07-03-dogfood-run-controls-design.md).

**Edit work item (title/priority/spec) — built.** The Detail screen header gained an **Edit**
button that opens an **Edit Work Item** modal (title · priority · spec), pre-filled from the item
and reusing the create-modal `Modal`/form primitives + `CreateModalProvider` (new `edit-work-item`
kind + `openEditWorkItem`). A new `useUpdateWorkItem` hook `PATCH`es `/work-items/{id}` and
invalidates the work-item/board/project queries; `PATCH /work-items/{id}` + the MSW mock
`db.updateWorkItem` already existed, so the write path is live-backed end to end and demoable in
mock mode. **UI-only** — no server change. First of the **B → A+C → D** "dogfood NAAF on itself"
sequence. Design: [superpowers/specs/2026-07-03-edit-work-item-design.md](superpowers/specs/2026-07-03-edit-work-item-design.md).

**Work-item thread (agent chat) — complete.** All three phases of the thread-as-substrate design
are shipped to `main` (Phase 1 #33 → Phase 2 #35 → Phase 3 #36): the work item is now the unit a
conversation is scoped to, one shared `<Thread>` renders across the Detail tab / inbox / sidebar,
runs narrate into the thread with gates as resolvable questions, and `@mention`s dispatch through
the bus so role-agents reply and coordinate agent↔agent (depth-guarded). Details in the entries
below; design: [superpowers/specs/2026-07-03-work-item-thread-substrate-design.md](superpowers/specs/2026-07-03-work-item-thread-substrate-design.md).

**A1 control plane — built.** Backend spine: Project + unified WorkItem (epic/feature/task)
with domain-enforced hierarchy and a status transition machine; owner-scoped
Repository/UnitOfWork (ported from hexrepo); envelope-aware CrudRouter; nested-create,
transition, and board APIs; config-only Team + AgentDefinition with a seed; Postgres + Alembic,
SQLite in tests; dev auth. See [superpowers/plans/2026-06-29-a1-control-plane.md](superpowers/plans/2026-06-29-a1-control-plane.md).

**A2 UI (mock-data SPA) — built (merged to `main`).** All 7 screens (Dashboard/Inbox/Board/List/Detail/Agent-Monitor/Settings) render from an OpenAPI-typed MSW mock layer; live-API swap deferred (A2-4). See [superpowers/plans/2026-06-29-a2-foundation.md](superpowers/plans/2026-06-29-a2-foundation.md) (+ the other `a2-*` plans).

**Creation modals (board write path) — built (merged to `main`, #32).** The board can now create work — the previously no-op **New** button is wired, plus board column `+` (seeded with that column's status), a board empty-state CTA, and a Sidebar **New project** button. Two modals ship: **Create Project** (name + repo URL) and **Create Work Item** with **Epic/Feature/Task** type tabs whose fields adapt per type (status, priority, parent epic/feature, spec) and a *Create & add another* action. Built on a new hand-rolled `Modal` design-system primitive + form primitives (`FormField`/`TextInput`/`Textarea`/`Select`), a `CreateModalProvider` React context that hosts the active modal, and `useCreateProject`/`useCreateWorkItem` mutation hooks that invalidate the board + work-items + projects queries so the board and sidebar counts refresh. Backend `POST /projects` and `POST /projects/{id}/work-items` (with hierarchy validation) already existed and are `liveHandlers`, so the write path is live-backed end to end; the MSW mock store was updated to persist created rows (and bump project `itemCount`) so mock mode reflects creates too. **Scope note:** Assign-Agent and Label at creation are deferred (the create API doesn't accept them). Design + plan: [superpowers/specs/2026-07-03-creation-modals-design.md](superpowers/specs/2026-07-03-creation-modals-design.md) · [superpowers/plans/2026-07-03-creation-modals.md](superpowers/plans/2026-07-03-creation-modals.md).

**Messaging foundation (A6 first slice) — built.** A conversational `Message` store + run-thread API: `GET /threads` (a thread = a run), `GET /threads/{id}/messages`, and `POST /threads/{id}/messages` (user→agent, **persist-only** — no bus publish yet). The inbox and the sidebar chat now share one live data source; the old `/inbox`/`InboxItem` mock is retired; notifications stay the separate alert channel. **Agents producing chat + the chat→bus bridge are deferred to the A5 runtime.** See [superpowers/plans/2026-07-02-messaging-foundation.md](superpowers/plans/2026-07-02-messaging-foundation.md).

**Work-item threads (Phase 1) — built.** Conversations are now scoped to a **work item**, not a run: one thread per work item (`thread_id == work_item_id`, no separate Thread table). The `messages` store was reshaped (`author_kind`/`author_role`/`model_alias`/`kind`/`mentions`/`payload`/`run_id`; migration `0009`), `/threads` became work-item-scoped (`GET /threads`, `GET /threads/{workItemId}`, `GET /threads/{workItemId}/messages`, `POST …/messages`), and a domain mention-parser extracts `@role` tokens (stored, **not yet dispatched**). On the UI, one shared kind-aware `<Thread>` component now renders across the Detail **Thread** tab (renamed from *Subagents*), the inbox pane (with a task-link banner), and the sidebar chat — "chat and inbox chat are the same." Humans can post; **agents don't reply yet** — Phase 2 has runs narrate into the thread (+ gates as `question` messages), Phase 3 adds `@mention` → bus dispatch so agents reply and coordinate. Design: [superpowers/specs/2026-07-03-work-item-thread-substrate-design.md](superpowers/specs/2026-07-03-work-item-thread-substrate-design.md); plan: [superpowers/plans/2026-07-03-work-item-thread-phase1.md](superpowers/plans/2026-07-03-work-item-thread-phase1.md).

**Work-item threads (Phase 2) — built.** The run pipeline now **narrates into the work-item thread**: a `narrate()` helper posts role-attributed `Message`s at run start, each stage result (with the agent's summary), and run finish — **additive** to the existing `RunEvent`/SSE stream (which is unchanged). Human gates render as resolvable **`question` messages** (`{options:[approve|reject], run_id, gate_kind, resolved_option}`); resolving one — via the inbox/thread **Option buttons** (new `POST /threads/{id}/messages/{msgId}/answer`) or the existing `POST /runs/{id}/gate` — publishes the same `GATE_RESOLVED` bus message, and the worker stamps `resolved_option` back onto the message (idempotent: a duplicate resolve is dropped by the `pending_gate is None` guard). The worker's `HandlerContext` gained a `messages` repository. On the UI, the (Phase-1-rendered) question Option buttons are now wired to an answer mutation and disable while resolving / once resolved. Still deferred to **Phase 3**: `@mention` → bus dispatch (agent↔agent), structured `file_write` cards from the runtime, loop guards. Plan: [superpowers/plans/2026-07-03-work-item-thread-phase2.md](superpowers/plans/2026-07-03-work-item-thread-phase2.md).

**Work-item threads (Phase 3) — built.** The thread is now the **live coordination substrate**: `POST /threads/{id}/messages` dispatches the message's `@role` mentions (or, with none, `@lead`) onto **work-item-scoped bus queues** (`wi:{id}:{role}`, new `MessageType.CHAT`). The worker's `handle_chat` wakes the role-agent through a `ChatResponder` port — **`EchoChatResponder`** (deterministic, offline/tests) or **`LlmChatResponder`** (reaches the model only via the existing `LLMAdapter`) — posts its reply into the thread, and **re-dispatches the reply's mentions** so agents coordinate agent↔agent. Runaway loops are bounded by a domain **depth guard** (`plan_dispatch(text, depth)` → `[]` at `MAX_FANOUT_DEPTH`; human posts start at depth 0, each agent hop increments; a would-be-infinite echo chain provably halts at an exact count), the existing one-in-flight-per-recipient bus invariant, and only `TEAM_ROLES` being addressable; an empty agent reply is skipped (no bubble, no fan-out). The default worker (`worker_roles=""`) claims every role. On the UI, the composer gained `@role` **mention chips**. This closes `docs/TODO.md` ("agents discover and dispatch messages to each other") and **completes the thread-as-substrate design** (Phases 1 #33 / 2 #35 / 3). Deferred (future): structured `file_write` cards, tools-in-chat (agents reading the repo mid-conversation), and a **per-thread message/token budget** to bound aggregate fan-out *width* (the depth guard bounds chain length, not width) — pairs with A5d. Plan: [superpowers/plans/2026-07-03-work-item-thread-phase3.md](superpowers/plans/2026-07-03-work-item-thread-phase3.md).

**Run monitor live + run usage tracking — built.** The Detail screen's run monitor is wired to the live A3 API: it renders `RunOut` (status, current stage, timestamps, stage timeline) and streams `RunEventOut` (event/log feed via SSE), with **Approve/Reject** controls resolving a pending gate (`POST /runs/{id}/gate`). Runs now track `token_usage` (accumulated from per-stage runtime output — deterministic in `FakeAgentRuntime`), surfaced as `tokenUsage` + a derived `cost` on `RunOut`. The run mocks were reshaped to the live contract behind `VITE_LIVE_API`; the mock `AgentRun`/`RunStep`/`LogLine` surface is retired. **Still mocked/deferred:** the `Agent`-entity dashboard/board panels and real per-model pricing (A5/A5d). See [superpowers/plans/2026-07-02-run-monitor-live.md](superpowers/plans/2026-07-02-run-monitor-live.md).

**A5 LLM-agnostic agent runtime — built.** The run pipeline now executes real work: a domain-owned, **LLM-agnostic** agent loop (`LlmAgentRuntime`) drives all six stages (`PROVISION → PLAN → IMPLEMENT → VERIFY → PR → LEARN` — PROVISION runs first so the repo is cloned before PLAN), reaching the model only through a single `LLMAdapter` port. Two adapters ship — **`ClaudeLLMAdapter`** (Anthropic SDK, default) and **`LiteLLMAdapter`** (OpenAI-compatible gateway) — chosen by `naaf_llm_provider`; per-role model selection flows from `AgentDefinition.model_alias`. Tools (read/write/edit/grep/bash) run through a `Workspace` port (`LocalWorkspace`); PROVISION clones the project repo + creates the `agent/<run>` branch; the PR stage captures the opened PR URL into a `RunEvent`; LEARN runs as the curator. Runs execute **locally in the worker** (no sandbox yet). This **supersedes the design's "Claude Code runtime adapter" framing** — we own the loop, so the whole project is provider-agnostic. Deferred: sandbox / egress / GitHub App (A4), budget enforcement (A5d), memory-diff review UI (A6). See [specs/2026-07-02-a5-llm-agnostic-agent-runtime-design.md](specs/2026-07-02-a5-llm-agnostic-agent-runtime-design.md) + the matching plan.

**A5 follow-ups (deferred, tracked):** a whole-branch review + Phase 8 hardening closed the run-blocking gaps (provision-before-plan ordering, a `report` tool so VERIFY can fail, halt-on-stage-failure, model-alias defaults, symmetric output cap, fail-fast credential checks). Remaining polish, not yet done: (1) persist the captured `pr_url` on the `Run` (today it's only a `RunEvent` payload); (2) thread `naaf_agent_bash_timeout_s` through to `LocalWorkspace.bash` (currently a hardcoded 120s); (3) apply `AgentDefinition.capability_grants` to filter the tool set (the loop passes the full `TOOL_SPECS`); (4) retire the now-misleading `_STUB_STAGES` / "stub" naming in `handlers.py` + `FakeAgentRuntime` (those stages are real now); (5) LiteLLM **per-run budget key** minting (spec §4.3/§9 — pairs with A5d budget enforcement). None block a single-user local run.

**Running it locally — `make dev`.** One command brings up the whole stack for testing/validation: Postgres + Redis (docker) → migrate + seed → **API** (`:8000`) + **worker** + **UI** (`:5173`, live-API), all sharing Postgres via `naaf_db_url`; `Ctrl-C` stops everything. It now defaults to the **`claude_code`** runtime (real agents — needs a Claude subscription or `naaf_anthropic_api_key=sk-...` exported). For a no-LLM, **zero-config** run (CI / no key), use `make dev NAAF_AGENT_RUNTIME=fake`, which drives a work-item end-to-end through `provision → plan → implement → verify → pr → learn → succeeded`. Needs Docker running and a one-time `cd projects/ui && pnpm install`.

**Containerized E2E worker — built (A4 slice 1).** The agent worker now runs as a **role-configured Docker service** (`Dockerfile` with `git` + the `gh` CLI + `uv`; an entrypoint that runs `gh auth setup-git` when `GH_TOKEN` is set) that executes the full end-to-end run inside a container — clone → real `LlmAgentRuntime` → the agent opens a PR via `gh` → curate. The `worker` compose service is wired with the E2E environment (`naaf_anthropic_api_key`, `naaf_workspace_root` on a `naaf_workspaces` volume, `GH_TOKEN`); `naaf_agent_runtime` defaults to **`fake`** (CI / no-key envs work) and opts into a real run with `claude_code`. **Role-filtered claiming** (`naaf_worker_roles` + `claim_next(roles)` + `BusSource`) scopes each worker; the one-in-flight-per-recipient invariant holds by **partitioning roles one-per-worker** (advisory-lock hardening for shared roles is a follow-up). **Deferred:** egress proxy / network hardening (A4 slice 3) and GitHub App per-run tokens (this slice uses a single `GH_TOKEN`). See [superpowers/plans/2026-07-03-worker-e2e.md](superpowers/plans/2026-07-03-worker-e2e.md).

**Bus adapter is now SQL-free — refactor.** The message bus's SQL was moved into a `BusMessageRepository` (in `adapters/database`), and `SqlMessageBus` is now a thin `MessageBus`-port adapter that delegates via `uow.bus_messages` — closing the last "SQL in an adapter" exception (per the persistence-isolation rule). The bus repository is deliberately **cross-owner / not owner-scoped** (a worker claims pending messages across all owners), following the `SubscriberCursorRepository` precedent. Pure refactor, behavior unchanged. See [superpowers/plans/2026-07-03-bus-repository-refactor.md](superpowers/plans/2026-07-03-bus-repository-refactor.md).

## Outstanding (not yet built)

The single-user local loop is complete; what remains is **hardening, the management plane, and the
full team**. In rough priority order:

- **A4 — sandbox / egress / network hardening.** The worker runs in Docker, but there is **no egress
  proxy or network isolation** (A4 slice 3), and agents get a single shared **`GH_TOKEN`** rather than
  **GitHub App per-run tokens**. This is the main gap before running untrusted/remote work.
- **A5d-2 — budget enforcement.** The display slice shipped (real per-model pricing, persisted
  `Run.cost`, live `/dashboard/metrics` + `/budget`). Remaining: a **settable per-owner `Budget`
  entity** + set-budget UI (today the limit is the `naaf_budget_limit_usd` config), the **worker
  halting/failing a run** when spend exceeds the cap, **monthly reset/periods** (today `used` is
  all-time), a **per-model spend breakdown**, and LiteLLM per-run budget-key minting. The
  thread-fan-out **per-thread message/token budget** also pairs here.
- **Live agent output — mostly shipped (PR #56); two small follow-ups.** The coarse activity trace
  streams into chat + runs today. Remaining: (1) token-by-token deltas via a Redis channel (the
  `agent_events` model is designed to add them without breaking changes); (2) optionally re-point the
  dashboard `/activity` feed at `agent_events` behind its unchanged contract.
- **C — rest of the management plane.** Secrets shipped; the **capabilities / MCP-server / model /
  budget** management UIs are not built.
- **B — full team.** The pipeline dispatches only **lead / engineer / qa**; architect / frontend /
  devops roles exist in the roster but are never run. Parallel engineers, deeper memory/RAG, and
  richer role coordination are future work.
- **A5 follow-up polish (tracked, non-blocking):** apply `AgentDefinition.capability_grants` to filter
  the tool set; thread `naaf_agent_bash_timeout_s` into `LocalWorkspace.bash`; retire the misleading
  `_STUB_STAGES` / "stub" naming; mint LiteLLM per-run budget keys (pairs with A5d).

The agent/sandbox content in the master design and architecture doc describes the **target**, not all
current code. **Orchestration is Local-First** (master design spec §2/§3): agents run locally in
Docker containers, exchanging messages via pub/sub onto per-agent queues, processed sequentially.
