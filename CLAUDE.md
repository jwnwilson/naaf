# NAAF — Not Another Agent Framework

Local tool for running a **virtual dev team** — role-based AI agents (team lead, architect, backend/frontend engineers, QA, devops) — against real repositories, driven from a visual kanban board of projects → epics → features → tasks. Agents work in sandboxed Docker containers with centrally managed secrets, permissions, skills, MCP servers, and models, produce reviewable PRs, and update persistent memory as they work.

- Design spec: [docs/specs/2026-06-12-naaf-design.md](docs/specs/2026-06-12-naaf-design.md)
- **Where we are (read first): [docs/project-history.md](docs/project-history.md)** — consolidated status, what's shipped, gaps
- Current plan: TBC

## Workflow (read first)

**All work happens in a git worktree and ships via a reviewed PR. Never commit or push directly to `main`.**

- **Always use a git worktree — never a fresh clone or a copied/duplicate repo.** A worktree
  shares the primary repo's `.git`; a duplicate clone clutters `~/projects` and drifts. If you
  catch yourself running `git clone` or `cp -r` of this repo, stop — use `git worktree add`.
- Start every task in an isolated worktree off the latest `main`, nested under `.worktrees/`:
  `git worktree add -b <type>/<slug> .worktrees/<slug> origin/main`. Do the work there, not in
  the primary checkout. (`.worktrees/` is git-ignored, so worktrees never show up as untracked
  files in the primary checkout.)
- When done, remove the worktree with `git worktree remove .worktrees/<slug>` (do not `rm -rf`
  it, which leaves a prunable stub).
- `main` only advances by merging a reviewed PR — no direct commits, no bundled auto-commits with junk titles.
- One PR = one focused change: a clear `<type>: <description>` title, a summary, and a test plan. Keep unrelated edits out.
- Before opening the PR, get `make coverage` (80% gate) and `make lint` green, then `git push -u origin <branch>` and open the PR with `gh pr create`.

## Stack

- Python ≥ 3.12, package manager: `uv`
- FastAPI + uvicorn (API), Pydantic v2, pydantic-settings (env prefix `naaf_`)
- SQLAlchemy 2.0 (sync) + Postgres 16 (SQLite in-memory for tests)
- Local-first run executor — agents run in docker containers and exchange messages via a pub/sub bus onto per-agent queues, processed sequentially (phase A3+).
- React + Vite + Tailwind (board UI in `ui/`; phase A2+)
- pytest + httpx; 80% coverage gate

## Architecture

> **When designing tasks that touch persistence or the API layer, first read
> [docs/architecture.md](docs/architecture.md)** — it defines the repository/UnitOfWork,
> owner-scoping, and CrudRouter patterns (adapted from hexrepo) that new code must follow.

Hexagonal, three layers — domain logic never touches I/O:

```
libs/
  crud_router/       # envelope-aware CrudRouter (workspace lib)
projects/
  server/            # Backend API service
    src/
      domain/        # pure business logic — Project, WorkItem, Team, AgentDefinition, transitions, hierarchy, board
      adapters/
        database/    # ports.py (Repository/UnitOfWork + PaginatedResult), orm.py, repository.py, repositories.py, uow.py, engine.py
      interactors/
        api/         # FastAPI wiring: app factory, routes, deps, auth, envelope, settings
        cli/         # seed
  ui/                # React/Vite/Tailwind SPA — reserved for A2 (planned layout below)
    app/             # app shell: providers, router, layout, error boundary
    modules/         # feature/domain slices (board, runs, manage, team, …); each owns its components + hooks + api
    components/ui/   # design-system primitives (Button, Dialog, Card, …) + shared composed components
    lib/api/         # typed envelope API client + per-domain modules + React Query key factories
```


> Placement rules: persistence ports (Repository/UnitOfWork protocols) live with their impl in `adapters/database/ports.py`; business logic in `domain/` (no argparse, no I/O, no adapter imports), with each entity model co-located in the domain module that owns it (no central `models.py`); port implementations in `adapters/`; reusable app-agnostic modules in `lib/`; wiring/startup in `interactors/`. No `scripts/` folder.

## Key conventions

- **Immutability**: Pydantic models updated via `model_copy(update={...})`, never mutated.
- **API envelope**: every response is `{success, data, error}` (+ `meta` for pagination).
- **Owner scoping**: every owned row carries `owner_id`; the UnitOfWork applies it as a required filter on every repository query. Auth mode `dev` injects `dev-user`; Auth0 arrives with the remote profile.
- **Status changes** go through `domain/transitions.validate_transition` — invalid transitions return HTTP 409.
- **Run IDs / entity IDs** are UUID hex strings (32 chars).
- **TDD**: write the failing test first; AAA structure; descriptive behavior names.
- Commit format: `<type>: <description>` (feat/fix/refactor/docs/test/chore/perf/ci).

## Dev commands

```bash
uv sync
docker compose up -d postgres redis
make db-upgrade            # alembic upgrade head
uv run python -m interactors.cli.seed
make test                  # uv run pytest
make coverage              # 80% gate
make run                   # uvicorn interactors.api.app:create_app --factory --reload
make worker                # Celery worker+beat; agent queue stays Postgres, Celery broker is Redis (scheduling only)
```

### UI (fully mocked — no backend needed)

```bash
cd projects/ui && pnpm dev   # VITE_USE_MOCKS=true is the default (.env)
```

### UI hybrid live-API mode (real backend for projects/work-items/teams/agent-definitions)

```bash
# terminal 1 — backend API
cd projects/server
docker compose -f ../../docker-compose.yml up -d postgres
make db-upgrade && uv run python -m interactors.cli.seed
make run                   # listens on :8000

# terminal 2 — run worker (A3+: drains the durable message bus, drives runs)
make worker                # naaf_db_url must point at the same Postgres as the API

# terminal 3 — UI with live API flag
cd projects/ui
VITE_LIVE_API=true pnpm dev
# Vite proxies /api → http://localhost:8000; /threads is now live
# (inbox + sidebar chat); MSW still handles runs/agents/dashboard/budget.
```

> **A3 run pipeline (backend, live):** `POST /work-items/{id}/runs` starts a run; the
> worker drives `plan → [✋plan gate] → implement → verify → [✋merge gate] → pr → learn`
> with `FakeAgentRuntime` (no LLM yet). Observe via `GET /runs/{id}`, `GET /runs/{id}/events`,
> the SSE stream `GET /runs/{id}/events/stream`, and resolve gates via
> `POST /runs/{id}/gate {"decision":"approve"|"reject"}`. The UI run/agent/inbox screens stay
> **mocked** for now — wiring them live needs a contract reconciliation (the mock-era
> `schema.d.ts` run/agent shapes diverge from the A3 `RunOut`/`RunEventOut`); tracked as an
> A3 follow-up.

## Status

**A1 control plane is built.** See [docs/project-history.md](docs/project-history.md) for what shipped, what is designed-only, and what comes next.

## Roadmap (phase A spine → C management plane → B full team)

A1 control-plane foundation ✓ → A2 UI (mock-data SPA, all 7 screens) ✓ → A3 agent run pipeline (**local pub/sub orchestration**) + FakeAgentRuntime → A4 sandbox/egress proxy/GitHub App → A5 Claude Code runtime adapter + LiteLLM → A5d token/usage tracking → A5e notification system → A6 refinement chat + memory. Then C (secrets/capabilities/model/budget UIs — budget builds on A5d usage data), then B (full team roles, parallel engineers, RAG).

> Orchestration is **Local-First** (master design spec §2/§3) — agents run locally in docker containers and exchange messages via a pub/sub bus onto per-agent queues, processed sequentially.
