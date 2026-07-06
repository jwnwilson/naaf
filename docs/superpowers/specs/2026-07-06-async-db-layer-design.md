# Async database layer (`libs/db`) — targeted at the SSE streams

**Date:** 2026-07-06
**Status:** Approved — ready for implementation planning
**Branch:** `feat/async-db-layer`

## Problem

The SSE activity-stream endpoints (`interactors/api/routes/activity.py` — the thread and
run activity streams — plus the run-events stream in `routes/runs.py`) are declared
`async def` but run **synchronous psycopg queries on the asyncio event loop**. Each open
stream polls the DB every ~0.3s inside `async def gen()` via the sync `SqlUnitOfWork`
(`uow.agent_events.list_after(...)`). While psycopg blocks on the Postgres socket, the
single event loop is frozen, so no other request is served.

This was confirmed live: a `sample` of the stuck API worker showed the event loop inside
`async_gen_asend_send → psycopg wait_c → poll`, and every endpoint (including a no-DB
`/health`) intermittently timed out while multiple UI panels held activity streams open.
The DB itself was healthy (13/100 connections, no locks) — the bottleneck is the event
loop, not Postgres.

## Goal

Give the async SSE generators an **async Unit of Work** backed by an async engine, so DB
round-trips no longer block the event loop. Everything else stays synchronous. Extract the
generic, domain-agnostic DB machinery into a reusable workspace lib that provides both a
sync and an async implementation (modeled on `hexrepo_db`).

## Non-goals (YAGNI)

- Converting sync `def` endpoints to async.
- Migrating the worker's message-drain loop to async (a background process; blocking is fine).
- Mirroring all 12 concrete repositories in async — only `AgentEventRepository` is needed now.
- Adding `asyncpg`. psycopg3 is both sync and async on the same `postgresql+psycopg://` URL.

## Decisions (from brainstorming)

1. **Scope:** targeted — only the async SSE stream endpoints use the async UoW. Sync and
   async UoWs coexist permanently.
2. **Lib boundary:** the new lib holds **generic machinery only**; the app keeps `orm.py`,
   the concrete repositories, and the concrete UoWs.
3. **Async depth:** a **complete** generic `AsyncSqlRepository` (full CRUD parity), but only
   **one** concrete async repo wired now (`AgentEventRepository.list_after`).
4. **Testing:** mirror the sync tests with in-memory `sqlite+aiosqlite://` + `StaticPool`,
   plus one Postgres-backed async smoke test.
5. **Driver:** reuse the existing `postgresql+psycopg://` URL via `create_async_engine`
   (psycopg3 async); add `greenlet` for SQLAlchemy's async bridge.

## Architecture

```
libs/db (package: naaf_db)  ── generic, domain-agnostic ─────────────────────
  engine.py       build_engine / build_session_factory              (sync, moved from app)
                  build_async_engine / build_async_session_factory  (new)
  repository.py   SqlRepository[DTO]        (sync — moved verbatim from the app)
                  AsyncSqlRepository[DTO]   (new — mirrors SqlRepository method-for-method)
  uow.py          SqlUnitOfWorkBase / AsyncUnitOfWorkBase
                    (transaction() sync/async + _repo(name, cls) helper + session mgmt)
  ports.py        PaginatedResult, Repository / AsyncRepository protocols,
                  UnitOfWork / AsyncUnitOfWork base protocols
  errors.py       RecordNotFound / IntegrityConflict  (lib-local; see "Domain purity")

projects/server/src/adapters/database  ── naaf-specific ─────────────────────
  orm.py          (unchanged)
  repository.py   thin: re-exports / binds lib bases to naaf's ORM Base + domain errors
  repositories.py 12 sync repos subclass the lib SqlRepository (behavior unchanged)
                  + AsyncAgentEventRepository (new — async list_after only)
  uow.py          SqlUnitOfWork    (subclasses SqlUnitOfWorkBase; named repo properties
                                    + delete_project_cascade unchanged)
                  + AsyncUnitOfWork (new; exposes .agent_events only)
  engine.py       thin re-export of the lib builders, keeping import paths stable
                  (e.g. `from adapters.database.engine import build_engine`)
```

### Data flow (after the change)

- **Sync request** (`def` endpoint) → FastAPI threadpool → `get_uow` → `SqlUnitOfWork`
  (sync engine/session) → psycopg sync. Unchanged.
- **SSE stream** (`async def`) → `get_async_uow` → `AsyncUnitOfWork` (async engine/session)
  → `await uow.agent_events.list_after(...)`. The event loop is free while Postgres works.
- **Worker** → `SqlUnitOfWork`. Unchanged.

## Component design

### `libs/db` — generic machinery

- **Session managers.** A sync manager (moved from the app's `engine.py`/`uow.py` pattern)
  and an async manager built on `create_async_engine` + `async_sessionmaker`. Each caches
  its engine and exposes a `transaction()` context manager that opens a session, commits on
  success, rolls back on exception, and closes. The async variant is an
  `@asynccontextmanager`. Engine construction stays minimal (no read-only pools, no engine
  map, no query-counting — those are `hexrepo_db` features this project does not need).
- **`SqlRepository[DTO]`** — moved verbatim from `adapters/database/repository.py`. Generic
  DTO-in/DTO-out CRUD with `required_filters` owner-scoping, the `__in/__like/__gte/...`
  filter suffixes, ordering, and `delete_where`.
- **`AsyncSqlRepository[DTO]`** — a faithful mirror: same query-building helpers, but
  `async def` methods that `await self.session.execute(...)`, `await self.session.flush()`,
  `await self.session.refresh(...)`. Full parity: `create/read/read_multi/update/delete/
  delete_where`.
- **UoW bases.** `SqlUnitOfWorkBase` and `AsyncUnitOfWorkBase` provide `transaction()`, the
  `_repo(name, cls)` memoization helper, and `session`. Concrete app UoWs subclass them and
  add named repository properties.

### Domain purity (exception binding)

`domain/` must not import from an infra lib. The lib defines its own `RecordNotFound` /
`IntegrityConflict` and the repository bases expose them as **overridable class attributes**:

```python
class SqlRepository(Generic[DTO]):
    not_found_error: type[Exception] = RecordNotFound      # lib default
    conflict_error: type[Exception] = IntegrityConflict
```

The app's concrete repository base (in `adapters/database/repository.py`) overrides these to
`domain.errors.RecordNotFound` / `domain.errors.IntegrityConflict`, so every existing
`except domain.errors.RecordNotFound` site keeps working and `domain` stays import-clean.

### App changes

- `adapters/database/repositories.py`: add `AsyncAgentEventRepository(AsyncSqlRepository)`
  with an async `list_after(scope, after, limit)` mirroring the sync one.
- `adapters/database/uow.py`: add `AsyncUnitOfWork(AsyncUnitOfWorkBase)` exposing only
  `.agent_events`. `SqlUnitOfWork` keeps all named properties and `delete_project_cascade`.
- `interactors/api/app.py`: build the async engine + `async_session_factory` at startup;
  store on `app.state`; add a FastAPI `lifespan` that `dispose()`s both engines on shutdown.
- `interactors/api/deps.py`: add `get_async_uow` (async dependency) mirroring `get_uow`.
- `interactors/api/routes/activity.py` and `routes/runs.py`: the `_stream` generator uses the
  async UoW and `await`s the read. Also add `if await request.is_disconnected(): return` so a
  closed stream stops looping (they currently run up to the 30-minute cap), reducing the
  stream buildup that amplified the freeze.

## Error handling

- Async `transaction()` rolls back and re-raises on any exception, then closes the session —
  same contract as the sync one.
- SSE generators keep their existing terminal handling (stop on `final`/`error` events); the
  new `is_disconnected()` check is an additional clean exit, not a behavior change to the
  event contract.
- The async engine is disposed on app shutdown via `lifespan` to avoid leaked connections.

## Testing

- `libs/db/tests/`: unit tests for `SqlRepository` (regression of moved code) and
  `AsyncSqlRepository` (create/read/read_multi/update/delete/delete_where + owner-scoping)
  against in-memory `sqlite://` and `sqlite+aiosqlite://` with `StaticPool`.
- App: `AsyncAgentEventRepository.list_after` test on aiosqlite; an async SSE integration
  test asserting the stream yields persisted events; **one Postgres-backed async smoke test**
  exercising `AsyncUnitOfWork` end-to-end (the freeze was Postgres-specific).
- `make coverage` stays ≥ 80%; `make lint` (ruff + mypy) green.

### New dependencies

- Runtime: `sqlalchemy[asyncio]` (pulls `greenlet`).
- Test: `aiosqlite`, `pytest-asyncio`.
- Workspace: add `libs/db` to `[tool.uv.workspace].members` and as a `naaf-db` source;
  add it to `projects/server` dependencies.

## What this fixes

The SSE stream generators no longer run blocking psycopg calls on the event loop. Under
multiple concurrent streams the loop stays responsive, so the API no longer intermittently
freezes and the UI can refresh. The `is_disconnected()` check stops orphaned streams from
looping for 30 minutes, further reducing loop load.

## Rollout

One PR on `feat/async-db-layer`: create the lib, move the sync machinery into it (import
paths preserved via re-exports), add the async implementation, wire the two stream endpoints,
and add tests. No migration, no data change, no worker change.
