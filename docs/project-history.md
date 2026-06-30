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

**Not yet built (designed only):** A3 agent run pipeline (**local pub/sub orchestration**) + runs · A4 sandbox /
egress / GitHub App · A5 Claude Code runtime + LiteLLM · B/C management plane. The
agent/sandbox/secrets content in the master design and architecture doc is the
*target*, not current code. **Orchestration is Local-First** (master design spec §2/§3): agents run locally in docker containers, exchanging messages via pub/sub onto per-agent queues, processed sequentially.
