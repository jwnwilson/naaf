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

## Status (2026-06-30)

**A1 control plane — built.** Backend spine: Project + unified WorkItem (epic/feature/task)
with domain-enforced hierarchy and a status transition machine; owner-scoped
Repository/UnitOfWork (ported from hexrepo); envelope-aware CrudRouter; nested-create,
transition, and board APIs; config-only Team + AgentDefinition with a seed; Postgres + Alembic,
SQLite in tests; dev auth. See [superpowers/plans/2026-06-29-a1-control-plane.md](superpowers/plans/2026-06-29-a1-control-plane.md).

**A2 UI (mock-data SPA) — built (merged to `main`).** All 7 screens (Dashboard/Inbox/Board/List/Detail/Agent-Monitor/Settings) render from an OpenAPI-typed MSW mock layer; live-API swap deferred (A2-4). See [superpowers/plans/2026-06-29-a2-foundation.md](superpowers/plans/2026-06-29-a2-foundation.md) (+ the other `a2-*` plans).

**Messaging foundation (A6 first slice) — built.** A conversational `Message` store + run-thread API: `GET /threads` (a thread = a run), `GET /threads/{id}/messages`, and `POST /threads/{id}/messages` (user→agent, **persist-only** — no bus publish yet). The inbox and the sidebar chat now share one live data source; the old `/inbox`/`InboxItem` mock is retired; notifications stay the separate alert channel. **Agents producing chat + the chat→bus bridge are deferred to the A5 runtime.** See [superpowers/plans/2026-07-02-messaging-foundation.md](superpowers/plans/2026-07-02-messaging-foundation.md).

**Run monitor live + run usage tracking — built.** The Detail screen's run monitor is wired to the live A3 API: it renders `RunOut` (status, current stage, timestamps, stage timeline) and streams `RunEventOut` (event/log feed via SSE), with **Approve/Reject** controls resolving a pending gate (`POST /runs/{id}/gate`). Runs now track `token_usage` (accumulated from per-stage runtime output — deterministic in `FakeAgentRuntime`), surfaced as `tokenUsage` + a derived `cost` on `RunOut`. The run mocks were reshaped to the live contract behind `VITE_LIVE_API`; the mock `AgentRun`/`RunStep`/`LogLine` surface is retired. **Still mocked/deferred:** the `Agent`-entity dashboard/board panels and real per-model pricing (A5/A5d). See [superpowers/plans/2026-07-02-run-monitor-live.md](superpowers/plans/2026-07-02-run-monitor-live.md).

**A5 LLM-agnostic agent runtime — built.** The run pipeline now executes real work: a domain-owned, **LLM-agnostic** agent loop (`LlmAgentRuntime`) drives all six stages (`PROVISION → PLAN → IMPLEMENT → VERIFY → PR → LEARN` — PROVISION runs first so the repo is cloned before PLAN), reaching the model only through a single `LLMAdapter` port. Two adapters ship — **`ClaudeLLMAdapter`** (Anthropic SDK, default) and **`LiteLLMAdapter`** (OpenAI-compatible gateway) — chosen by `naaf_llm_provider`; per-role model selection flows from `AgentDefinition.model_alias`. Tools (read/write/edit/grep/bash) run through a `Workspace` port (`LocalWorkspace`); PROVISION clones the project repo + creates the `agent/<run>` branch; the PR stage captures the opened PR URL into a `RunEvent`; LEARN runs as the curator. Runs execute **locally in the worker** (no sandbox yet). This **supersedes the design's "Claude Code runtime adapter" framing** — we own the loop, so the whole project is provider-agnostic. Deferred: sandbox / egress / GitHub App (A4), budget enforcement (A5d), memory-diff review UI (A6). See [specs/2026-07-02-a5-llm-agnostic-agent-runtime-design.md](specs/2026-07-02-a5-llm-agnostic-agent-runtime-design.md) + the matching plan.

**A5 follow-ups (deferred, tracked):** a whole-branch review + Phase 8 hardening closed the run-blocking gaps (provision-before-plan ordering, a `report` tool so VERIFY can fail, halt-on-stage-failure, model-alias defaults, symmetric output cap, fail-fast credential checks). Remaining polish, not yet done: (1) persist the captured `pr_url` on the `Run` (today it's only a `RunEvent` payload); (2) thread `naaf_agent_bash_timeout_s` through to `LocalWorkspace.bash` (currently a hardcoded 120s); (3) apply `AgentDefinition.capability_grants` to filter the tool set (the loop passes the full `TOOL_SPECS`); (4) retire the now-misleading `_STUB_STAGES` / "stub" naming in `handlers.py` + `FakeAgentRuntime` (those stages are real now); (5) LiteLLM **per-run budget key** minting (spec §4.3/§9 — pairs with A5d budget enforcement). None block a single-user local run.

**Running it locally — `make dev`.** One command brings up the whole stack for testing/validation: Postgres + Redis (docker) → migrate + seed → **API** (`:8000`) + **worker** + **UI** (`:5173`, live-API), all sharing Postgres via `naaf_db_url`; `Ctrl-C` stops everything. It defaults to the no-LLM `FakeAgentRuntime` so runs execute end-to-end with **zero config** — validated by driving a work-item through `provision → plan → implement → verify → pr → learn → succeeded`. For the real LLM runtime: `make dev NAAF_AGENT_RUNTIME=claude_code naaf_anthropic_api_key=sk-...` (exported). Needs Docker running and a one-time `cd projects/ui && pnpm install`.

**Containerized E2E worker — built (A4 slice 1).** The agent worker now runs as a **role-configured Docker service** (`Dockerfile` with `git` + the `gh` CLI + `uv`; an entrypoint that runs `gh auth setup-git` when `GH_TOKEN` is set) that executes the full end-to-end run inside a container — clone → real `LlmAgentRuntime` → the agent opens a PR via `gh` → curate. The `worker` compose service is wired with the E2E environment (`naaf_anthropic_api_key`, `naaf_workspace_root` on a `naaf_workspaces` volume, `GH_TOKEN`); `naaf_agent_runtime` defaults to **`fake`** (CI / no-key envs work) and opts into a real run with `claude_code`. **Role-filtered claiming** (`naaf_worker_roles` + `claim_next(roles)` + `BusSource`) scopes each worker; the one-in-flight-per-recipient invariant holds by **partitioning roles one-per-worker** (advisory-lock hardening for shared roles is a follow-up). **Deferred:** egress proxy / network hardening (A4 slice 3) and GitHub App per-run tokens (this slice uses a single `GH_TOKEN`). See [superpowers/plans/2026-07-03-worker-e2e.md](superpowers/plans/2026-07-03-worker-e2e.md).

**Not yet built (designed only):** A4 sandbox /
egress / GitHub App · B/C management plane. The
agent/sandbox/secrets content in the master design and architecture doc is the
*target*, not current code. **Orchestration is Local-First** (master design spec §2/§3): agents run locally in docker containers, exchanging messages via pub/sub onto per-agent queues, processed sequentially.

**`Run` is a defined domain entity but has no code yet.** A run = one execution of a task through the agent pipeline (`PLAN → … → LEARN`); it is specified in design spec §4 (Domain model) and §6 (Execution flow), but there is no `Run` model, persistence, API, or status machine in `projects/server/src` — it arrives with A3. Today only Project + WorkItem + Team/AgentDefinition exist in code.
