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

**Not yet built (designed only):** A3 agent run pipeline (**local pub/sub orchestration**) + runs · A4 sandbox /
egress / GitHub App · A5 Claude Code runtime + LiteLLM · B/C management plane. The
agent/sandbox/secrets content in the master design and architecture doc is the
*target*, not current code. **Orchestration is Local-First** (master design spec §2/§3): agents run locally in docker containers, exchanging messages via pub/sub onto per-agent queues, processed sequentially.

**`Run` is a defined domain entity but has no code yet.** A run = one execution of a task through the agent pipeline (`PLAN → … → LEARN`); it is specified in design spec §4 (Domain model) and §6 (Execution flow), but there is no `Run` model, persistence, API, or status machine in `projects/server/src` — it arrives with A3. Today only Project + WorkItem + Team/AgentDefinition exist in code.
