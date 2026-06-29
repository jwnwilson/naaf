# A1 Control Plane — Design

**Date:** 2026-06-29
**Status:** Approved design, pending implementation plan
**Milestone:** Phase A1 (control-plane foundation)
**Supersedes status claims in:** `CLAUDE.md`, `docs/architecture.md`, `docs/project-history.md` (reconciled as part of this milestone)

## 1. Context & reality check

NAAF's `docs/` describe an ambitious, largely "already-built" system (the master design
`docs/specs/2026-06-12-naaf-design.md`, plus `architecture.md` and `CLAUDE.md` claiming
phases A4a/A5a/A5b/A5c "merged", referencing ADR-0001/0002, `docs/plans/`, deployment
workflows). **None of that code exists.** This checkout is a true greenfield: `projects/` is
empty, there is no `src/`/`libs/`/`ui/`, no `pyproject.toml`, no Makefile, and `docs/adr/`
holds only `README.md` + `template.md`. Git history is a single "Initial commit".

The approved master design remains the *target vision*. This document defines the **first
real milestone (A1)** — the backend control-plane spine — and reconciles the stale status
docs to reflect greenfield reality.

`hexrepo` (`/Users/noel/projects/hexrepo`) is the structural reference. We **borrow its
hexagonal patterns and code** (Repository/UnitOfWork from `libs/db`, `CrudRouter` from
`libs/api`, the `{success,data,error}` envelope) but **not its tooling** (no `hextech`
scaffolding CLI, no CodeArtifact publishing, no Terraform). Single `uv` workspace.

## 2. Scope

### In scope (A1)

The backend spine, no agents:

- Domain model: `Project` + unified `WorkItem` hierarchy (epic/feature/task).
- Status state machine + transition validation.
- Hierarchy-integrity validation (epic→feature→task), domain-enforced.
- Full CRUD per entity; nested creation under a project; board read API.
- `{success, data, error}` envelope with `meta` pagination on lists.
- Owner-scoping on every owned row via UnitOfWork `required_filters`.
- Postgres 16 + Alembic migrations (SQLite in-memory for tests).
- Dev auth (`owner_id="dev-user"`); Auth0 slot left unbuilt.
- `Team` + `AgentDefinition` as **config-only** CRUD entities (+ seeded default team).
- Reconciling the three stale status docs to greenfield reality.

### Out of scope (deferred — designed, not built)

- React board UI → **A2** (consumes this API).
- Temporal, runs, the agent pipeline → **A3**.
- Docker sandbox, egress proxy, GitHub App → **A4**.
- Claude Code runtime adapter, LiteLLM → **A5**.
- Secrets / MCP / skills / RAG registries, budgets → **B/C**.

No agents, no LLM calls, no containers, no Temporal in A1. `Team`/`AgentDefinition` store
config but execute nothing.

## 3. Repo structure (lean uv workspace)

```
naaf/
  pyproject.toml            # uv workspace root (members: projects/server, libs/crud_router)
  Makefile                  # coverage (80% gate), lint, run, db-reset/db-upgrade
  docker-compose.yml        # postgres only (A1)
  ruff.toml / mypy config
  libs/
    crud_router/            # envelope-aware CrudRouter (port of hexrepo libs/api crud.py)
      pyproject.toml
      src/crud_router/
      tests/
  projects/
    server/
      pyproject.toml
      src/
        domain/             # pure business logic, no I/O
          project.py
          work_item.py      # WorkItem model + WorkItemKind + WorkItemStatus
          transitions.py    # validate_transition
          hierarchy.py      # validate_hierarchy(child_kind, parent)
          team.py           # Team + AgentDefinition models (config-only)
          errors.py
        adapters/
          database/
            ports.py        # Repository / UnitOfWork Protocols + PaginatedResult
            orm.py          # SQLAlchemy 2.0 declarative rows
            repository.py   # generic SqlRepository[DTO]
            repositories.py # thin per-entity subclasses
            uow.py          # SqlUnitOfWork (session + transaction + required_filters)
            engine.py       # engine + session_factory construction
        interactors/
          api/
            app.py          # app factory: engine, routers, exception handlers, auth
            deps.py         # per-request UoW dependency (owner-scoped)
            auth.py         # dev-mode owner_id injection
            envelope.py     # {success, data, error} (+ meta) helpers
            routes/         # project, work_item, team routers + hand-written routes
            settings.py     # pydantic-settings, env prefix naaf_
          cli/
            seed.py         # seed default team
        migrations/         # alembic (env.py + versions/)
      tests/
        domain/             # pure unit tests
        api/                # integration tests on SQLite in-memory
  docs/                     # existing docs (reconciled) + this spec
```

`libs/crud_router` is the one genuinely app-agnostic, reusable piece, so it is a real
path-dependency package in the workspace. The `ui/` slot is reserved for A2 and **not
created** in A1.

## 4. Domain model (pure, no I/O)

All models are Pydantic v2, updated immutably via `model_copy(update={...})`, never mutated.
IDs are UUID hex strings (32 chars). Every owned entity carries `owner_id`.

### Project

`id`, `owner_id`, `name`, `repo_url` (nullable), `repo_path` (nullable), `team_id`
(nullable until A3), `autonomy_level` (enum, default `gated_all`), `created_at`,
`updated_at`.

### WorkItem (unified hierarchy)

`id`, `owner_id`, `project_id`, `parent_id` (nullable), `kind` (`WorkItemKind` ∈
`epic|feature|task`), `title`, `body` (markdown), `acceptance_criteria`
(`list[AcceptanceCriterion]`, structured), `status` (`WorkItemStatus`), `created_at`,
`updated_at`.

### Status state machine

`WorkItemStatus` ∈ `to_do → in_progress → in_review → approved → done`, plus `blocked` and
`failed`. `domain/transitions.py::validate_transition(current, next) -> WorkItemStatus`
returns the new status or raises `InvalidTransition`. Single source of truth; the exact legal
edges (including how `blocked`/`failed` enter and resume) are enumerated in the
implementation plan.

### Hierarchy integrity (domain rule, parent passed in)

`domain/hierarchy.py::validate_hierarchy(child_kind, parent: WorkItem | None)` is **pure** —
the API/interactor fetches the parent row and passes it in, keeping domain I/O-free. Rules:

- `epic` → `parent` must be `None` (root under a project).
- `feature` → `parent.kind` must be `epic`.
- `task` → `parent.kind` must be `feature`.

Violations raise `InvalidHierarchy` (→ HTTP 409).

### Team + AgentDefinition (config-only)

`Team`: `id`, `owner_id`, `name`, list of `AgentDefinition`. `AgentDefinition`: `role`
(lead/architect/backend/frontend/qa/devops/custom), `persona_prompt`, `model_alias`,
`runtime_adapter`, `capability_grants` (deny-by-default placeholder), `memory_scope`. Stored
and CRUD-able in A1; consumed by execution only in A3. A default team (lead+engineer+QA) is
seeded via `cli/seed.py`.

### Errors

`domain/errors.py`: `RecordNotFound`, `IntegrityConflict`, `InvalidTransition`,
`InvalidHierarchy`.

## 5. Persistence (ported from hexrepo `libs/db`, sync-only)

- **`ports.py`** — `Repository[DTO]` + `UnitOfWork` `typing.Protocol`s and
  `PaginatedResult[DTO]` (`results`, `total`, `page_size`, `page_number`). These are
  infrastructure contracts, co-located with the impl, **not** in `domain/`.
- **`repository.py`** — one generic `SqlRepository[DTO]`:
  - DTO-in / DTO-out: `dto(**row.__dict__)` on read, `orm_model(**dto.model_dump())` on
    create; updates copy non-relationship attrs from the DTO onto the loaded row.
  - Filter DSL on `list()`: plain key = equality; suffixes `__in`, `__like` (ilike
    contains), `__isnull`, `__gt`, `__gte`, `__lt`, `__lte`, `__ne`. Roots =
    `{"parent_id__isnull": True}`.
  - Pagination: `page_size` / `page_number` (1-based) + `order_by` (`-created_at` =
    descending default); `list()` returns `PaginatedResult[DTO]` with `total` always
    computed.
  - Typed errors, never `None`/`bool`: `get`/`update`/`delete` raise `RecordNotFound`;
    constraint violations raise `IntegrityConflict`.
- **`repositories.py`** — thin declarative subclasses: `ProjectRepository`,
  `WorkItemRepository`, `TeamRepository`, `AgentDefinitionRepository`.
- **`uow.py`** — `SqlUnitOfWork(session_factory, required_filters={"owner_id": user_id})`:
  owns the session and one `transaction()` per request; repositories hang off it as
  properties sharing that session. `required_filters` auto-apply to every query (single,
  list, total) → owner-scoping enforced centrally; routes never hand-write `owner_id`
  checks. Cross-tenant access uniformly surfaces as `RecordNotFound` → 404.
- **`engine.py`** — the app factory builds the engine + `session_factory` once at startup
  (`app.state`); the per-request dependency constructs the owner-scoped UoW. No module-level
  engine map. Postgres is migrated by **Alembic** (`migrations/versions/`);
  `Base.metadata.create_all` is retained only for SQLite in-memory tests (`StaticPool`,
  `check_same_thread=False`).

## 6. API (ported from hexrepo `libs/api`)

- **`app.py`** factory builds engine/session_factory, mounts routers, registers exception
  handlers, and wires dev-auth.
- **`libs/crud_router` `CrudRouter`** registers standard routes per entity: `POST /` (201),
  `GET /{id}`, `GET /` (paginated; `filters` JSON query param, `page_size`, `page_number`,
  `order_by`), `PATCH /{id}`, `DELETE /{id}`.
- **Hand-written routes** on the same routers (override mechanism):
  - `POST /projects/{id}/work-items` — nested creation: fetches parent (if any), calls
    `validate_hierarchy`, denormalizes `owner_id`/`project_id`, creates atomically.
  - `POST /work-items/{id}/transition` — calls `validate_transition`.
  - `GET /projects/{id}/board` — returns the project's work-item tree for the board.
- **Envelope:** every response is `{success, data, error}`; list endpoints add
  `meta = {total, page_size, page_number}`. Exception→HTTP mapping is registered once in the
  factory:

  | Exception | HTTP |
  |---|---|
  | `RecordNotFound` | 404 |
  | `IntegrityConflict` | 409 |
  | `InvalidTransition` | 409 |
  | `InvalidHierarchy` | 409 |
  | `pydantic.ValidationError` (domain construction) | 422 |
  | `RequestValidationError` / `HTTPException` | 422 / passthrough |

- **`auth.py`** — dev mode injects `owner_id="dev-user"`; the request dependency builds the
  UoW with `required_filters={"owner_id": owner_id}`. Auth0 slot left for later, unbuilt.

## 7. Testing (TDD, 80% gate)

- **Unit (domain):** transition machine, hierarchy validation, model immutability — write
  the failing test first, AAA structure, behavior-named.
- **Integration (API + persistence):** endpoints against **SQLite in-memory**; assert
  envelope shape, owner-scoping (cross-owner → 404), atomic nested creation, pagination
  `meta`, transition 409s, hierarchy 409s.
- `make coverage` enforces the 80% gate; `make lint` runs ruff + type checking. Postgres via
  docker-compose is for manual/dev use, not required by the test suite.

## 8. Docs reconciliation (part of this milestone)

- **`CLAUDE.md`** — remove "A4a/A5 merged" claims and the orchestration "implemented"
  language; state honestly "A1 in progress; A2+ designed, not built"; fix the structure
  block to the lean layout above.
- **`docs/architecture.md`** — reframe from "is implemented" to "target patterns". The
  persistence/API sections stay (they are the A1 plan); the agent/Temporal/storage sections
  are marked "designed, A3+".
- **`docs/project-history.md`** — rewrite as an accurate status: greenfield → A1 underway,
  with an explicit list of what does not yet exist.
- Stale references (ADR-0001/0002, `docs/plans/`, deployment workflow) are removed or marked
  not-yet-existing. ADRs are created only when a real decision is made — A1 introduces
  **ADR-0001: lean single-`uv`-workspace structure (no hextech tooling)**.

## 9. Build order (first initial steps)

Each numbered step is a small, reviewable commit on the `feat/a1-control-plane` branch.

1. **Workspace scaffold** — root `pyproject.toml` (uv workspace), `projects/server`,
   `libs/crud_router`, Makefile, `docker-compose.yml` (postgres), ruff/mypy config.
2. **Domain core (TDD)** — `Project`, `WorkItem`, `WorkItemKind`, `WorkItemStatus`,
   `transitions.py`, `hierarchy.py`, `errors.py`; pure, fully unit-tested (green before any
   I/O).
3. **Persistence** — `ports.py`, `orm.py`, generic `SqlRepository`, `repositories.py`,
   `uow.py`, `engine.py`, Alembic baseline; repository/UoW integration tests on SQLite.
4. **API foundation** — `libs/crud_router` port, `envelope.py`, exception handlers,
   `auth.py`, `app.py` factory, `deps.py`.
5. **Routes** — CRUD routers + hand-written nested-creation / transition / board routes;
   API integration tests.
6. **Team config** — `Team` + `AgentDefinition` models, repos, routers; `cli/seed.py`
   default team.
7. **Docs** — reconcile the three status docs; add ADR-0001.
8. **Green + PR** — `make coverage` (80%) and `make lint` pass; open the A1 PR.

## 10. Error handling & conventions (carried from master design)

- Every external system stays behind a port with typed domain errors; no silent swallowing.
- User-facing errors are friendly via the envelope; full context goes to server logs.
- Immutability everywhere (`model_copy`); UUID hex IDs; commit format
  `<type>: <description>`; one focused PR for A1.
