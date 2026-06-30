# NAAF Architecture

> **Read this before designing any task that touches persistence or the API layer.**
> It defines the patterns (adapted from `hexrepo` `libs/db` + `libs/api`) that all new code
> must follow.
>
> For *where the project is* (what's shipped, what's dormant, what's missing), read
> [project-history.md](project-history.md) first. This file is patterns; that file is status.

## Layering (hexagonal)

Layout as built in A1 (future phases add the commented folders):

```
libs/
  crud_router/         # envelope-aware CrudRouter (workspace lib)
projects/
  server/              # Backend API service
    src/
      domain/          # pure business logic, no I/O — each entity model lives with its logic
      adapters/        # ports + adapters for the hexagonal approach
        database/      # ports.py (Repository/UnitOfWork + PaginatedResult), orm.py, repository.py, repositories.py, uow.py, engine.py
        # storage/     # designed; not built — A4+
      interactors/     # how code is initialised via API / worker / cli
        api/           # FastAPI wiring: app factory, routes, deps, auth, envelope, settings
        cli/           # seed
        # runs/        # designed; not built — A3+ (local run executor: agent message bus, per-agent queues, worker, run-state store)
  ui/                  # React/Vite/Tailwind SPA — reserved for A2
```

Placement rules: domain never imports adapters or interactors; routes contain wiring only;
all business rules (validation, transitions, orchestration policy, capability/invocation
composition) stay in domain. Ports live beside the adapter that implements them.

**Persistence ports live with the adapter that implements them** (`adapters/database/ports.py`),
not in `domain/`. The `Repository`/`UnitOfWork` protocols are generic persistence contracts
the domain never references — they exist so consumers (routes, DI) depend on an abstraction
rather than the concrete SQLAlchemy classes. Keeping them beside `repository.py`/`uow.py`
reflects what they actually are: infrastructure interfaces, not domain ports. A true domain
port (a business-meaningful capability the domain itself calls out to) would still live in
`domain/`.

**Reusable modular code goes in `lib/`.** When a component is generic infrastructure
rather than feature logic — something another feature (or project) could reuse unchanged,
like the `CrudRouter` factory — it belongs in `lib/`, not buried in `interactors/`. Keep
`lib/` modules as decoupled as practical so they read as a small internal toolkit.

## Persistence: Repository + Unit of Work (from hexrepo libs/db)

### Generic repository

One generic `SqlRepository[DTO]` (in `adapters/database/repository.py`)
implements CRUD for every entity; per-entity repositories are thin declarative
subclasses:

```python
class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project
```

Key behaviors (ported from `hexrepo_db.sql.repository.SQLRepository`, sync-only):

- **DTO in / DTO out.** Repositories accept and return domain Pydantic models, never
  ORM rows. Mapping is `dto(**row.__dict__)` on read and `orm_model(**dto.model_dump())`
  on create. Updates copy non-relationship attrs from the DTO onto the loaded row.
- **Filter DSL** on `list()`: plain key = equality; suffixes `__in`, `__like`
  (ilike contains), `__isnull`, `__gt`, `__gte`, `__lt`, `__lte`, `__ne`.
  `__isnull` replaces the old truthiness check — "root work items" is
  `{"parent_id__isnull": True}`.
- **Pagination**: `page_size` / `page_number` (1-based) + `order_by`
  (`-created_at` = descending, default). `list()` returns
  `PaginatedResult[DTO]` (`results`, `total`, `page_size`, `page_number`) — `total` is
  always computed so the UI can render page counts.
- **Typed errors, not None/bool**: `get`/`update`/`delete` raise
  `domain.errors.RecordNotFound`; constraint violations raise
  `domain.errors.IntegrityConflict`. Routes never branch on `None`.

### Unit of Work

`SqlUnitOfWork` (in `adapters/database/uow.py`) owns the session and transaction
boundary; repositories hang off it as properties sharing that one session:

```python
with uow.transaction():
    run = uow.runs.create(Run(task_id=task.id, team_id=project.team_id))
    uow.work_items.update(task.id, task.model_copy(update={"status": IN_PROGRESS}))
# both writes commit or roll back together
```

- One `transaction()` per request (provided by the API dependency). This fixes the
  A1 gap where each store method opened its own transaction (non-atomic run creation).
- The app factory owns the engine and `session_factory` (`app.state`, built once at
  startup via `adapters/database/engine.py`); the per-request dependency builds a
  `SqlUnitOfWork(session_factory, required_filters=...)`. No module-level engine map
  (hexrepo needs one for Lambda reuse; a long-lived FastAPI process does not). SQLite
  in-memory keeps `StaticPool` + `check_same_thread=False` for tests.
- **Alembic owns the schema** (`migrations/versions/`). `Base.metadata.create_all(engine)`
  remains for SQLite in-memory tests and ephemeral dev; Postgres is migrated. `make db-reset`
  clears the Postgres volume, runs `alembic upgrade head`, and re-seeds via `cli/seed.py`.

### Owner scoping via required filters

Hexrepo's `required_filters` mechanism is our owner-scoping enforcement: the API
dependency constructs the UoW with `required_filters={"owner_id": current_user_id}`,
and every repository query (single, list, total) automatically applies them. Routes
never hand-write `owner_id` checks.

To make this work, **every owned row carries `owner_id` — including `work_items` and
`runs`** (denormalized from the project at create time). This closes the deferred A1
gap where item-level work-item routes and run list/get were unscoped. Cross-tenant
access uniformly surfaces as `RecordNotFound` → 404.

## Storage port (blobs / run workspaces)

> **Designed; not built — A3+/A4+.** This section describes the target pattern for blob storage.
> No `adapters/storage/` code exists yet.

Non-relational blob storage (run workspaces, stage artifacts like `plan.md`/`progress.md`)
will use a **port co-located with its adapter**, the same convention as the database ports:

- `adapters/storage/ports.py` — `StoragePort` (a `typing.Protocol`):
  `write_bytes` / `read_text` / `exists` / `delete` / `delete_directory` / `local_path`.
  Keys are relative paths (`runs/{run_id}/plan.md`).
- `adapters/storage/local.py` — `LocalStorageAdapter(base_dir)` resolves keys under a base
  directory on the local filesystem (A3 backend).
- `adapters/storage/s3.py` — `S3StorageAdapter` (boto3) is the planned A4 backend; because
  callers depend only on `StoragePort`, swapping it in needs no code changes elsewhere.

A run's workspace will be the prefix `runs/{run_id}/`: the run executor derives the working
directory via `storage.local_path(...)` and reclaims it on terminal states via
`storage.delete_directory(...)`. Placement rule: the storage port will live in
`adapters/storage/ports.py`, not in `domain/`.

## API layer (from hexrepo libs/api)

### CrudRouter

`libs/crud_router` provides an envelope-aware port of hexrepo's
`CrudRouter`: a factory that registers standard CRUD routes for a UoW repository name —

```python
router = CrudRouter(
    repository="projects",
    response_dto=Project,
    create_schema=CreateProject,
    update_schema=UpdateProject,
    prefix="/projects",
    methods=["CREATE", "READ", "UPDATE", "DELETE"],
)
```

— generating `POST /` (201), `GET /{id}`, `GET /` (paginated list with `filters`
JSON query param, `page_size`, `page_number`, `order_by`), `PATCH /{id}`,
`DELETE /{id}`. Routes it can't express (nested creation under a project, status
transitions, run start, default team) are written by hand on the same router using
the override mechanism (`remove_api_route` + standard decorators), exactly as hexrepo
allows.

### Exception → HTTP mapping in one place

Routes and CrudRouter handlers do **not** try/except persistence errors. The app
factory registers exception handlers once:

| Exception | HTTP | Source |
|---|---|---|
| `domain.errors.RecordNotFound` | 404 | repository |
| `domain.errors.IntegrityConflict` | 409 | repository (constraint violations) |
| `domain.transitions.InvalidTransition` | 409 | state machine |
| `pydantic.ValidationError` (domain construction) | 422 | domain model validators |
| `RequestValidationError` / `HTTPException` | 422 / passthrough | FastAPI (existing) |

All handlers emit the envelope.

### Envelope and pagination meta (naaf convention, kept)

Every response stays `{success, data, error}`. List endpoints put
`PaginatedResult` bookkeeping into `meta`: `{"total": .., "page_size": ..,
"page_number": ..}` — uniform across all list endpoints (closes the A1
meta-inconsistency deferral).

## Agent execution & orchestration

> **Designed; not built — A3+/A4+.** This section describes the target orchestration
> architecture. No run executor, agent runtimes, or capability code exist yet.

Orchestration is **Local-First** (master design spec §2/§3): each agent runs locally in its
own docker container with its own context, secrets, MCP servers, tools, and model. Agents
exchange messages via a **pub/sub** pattern onto a **per-agent queue**; an agent drains its
queue **sequentially**, then either converses (with a user or another agent) or works on the
repository. The team lead acts as the orchestrator agent — it dispatches other agents and
reacts to their messages. The run executor is a **local message-bus / queue process** that
runs in-cluster alongside the agents. Domain stays pure: the non-deterministic decisions live
in `domain/`; the executor adapter carries them out and persists run state.

### Ports & adapters (deny-by-default execution)

- **`AgentRuntime`** (`domain/agent/runtime.py`) — event-streaming port: a stage/step runs a
  real agent and yields `AgentEvent`s + a `StageResult` (with token `usage`). Impls:
  `ClaudeCodeRuntime` (spawns `claude -p --output-format stream-json`) and `FakeAgentRuntime`
  (scripted events, no LLM). Auto-selected by key/binary availability.
- **`ModelProvider`** (`adapters/agent/model/`) — `anthropic` (direct) or `litellm` (gateway
  with per-agent `model_alias`); chosen by `model_gateway` setting.
- **Capability composition is pure.** `domain/agent/capabilities.py` selects the agent for a
  stage (role↔stage) and assembles an `AgentManifest` from its grants; `domain/agent/
  invocation.py::build_invocation()` turns the manifest + resolved registry rows into the exact
  `claude` invocation (argv, `--append-system-prompt`, allowed tools, `settings.json` hook,
  `.mcp.json`, `naaf_*` env, skills as (name, source, dest)). The adapter only does I/O: fetch
  skills, write files, spawn, parse. **Deny-by-default** is enforced twice — static
  `--allowedTools` and an active **PreToolUse hook** (`domain/permissions.py` decides;
  `adapters/agent/runtime/pretooluse_hook.py` enforces and logs to `audit.jsonl`).
- **Secrets** are Fernet-encrypted, write-only, and decrypted *inside the executor adapter* into
  `manifest.secret_env` — injected into the subprocess + per-MCP `env`, never serialized into
  run inputs, run events, or logs.

