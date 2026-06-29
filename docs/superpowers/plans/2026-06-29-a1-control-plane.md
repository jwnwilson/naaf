# A1 Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build NAAF's backend control-plane spine — a FastAPI service exposing CRUD + board APIs over a Project → (Epic/Feature/Task) work-item hierarchy, with owner-scoped persistence, a status state machine, and config-only Team entities — no agents, no Temporal, no LLM.

**Architecture:** Hexagonal. Pure `domain/` (Pydantic v2 models, transition + hierarchy rules) never touches I/O. `adapters/database/` ports a sync Repository + UnitOfWork from hexrepo `libs/db` with owner-scoping via required filters. `interactors/api/` wires FastAPI: a `{success,data,error}` envelope, an envelope-aware `CrudRouter` (in `libs/crud_router`, ported from hexrepo `libs/api`), and hand-written nested-creation / transition / board routes. Postgres + Alembic in dev; SQLite in-memory for tests.

**Tech Stack:** Python ≥3.12, `uv` workspace, FastAPI + uvicorn, Pydantic v2 + pydantic-settings, SQLAlchemy 2.0 (sync) + psycopg3, Alembic, pytest + httpx + pytest-cov, ruff + mypy.

## Global Constraints

- Python `>=3.12`; package manager `uv` (never pip/poetry); UI package manager would be pnpm (not in A1).
- Pydantic v2 models updated **immutably** via `model_copy(update={...})`, never mutated.
- Every API response is the envelope `{success: bool, data: T | None, error: str | None}`; list endpoints add `meta: {total, page_size, page_number}`.
- Every owned row carries `owner_id`; the UnitOfWork applies it as a required filter on every query and stamps it on every create. Cross-owner access surfaces as `RecordNotFound` → 404.
- Entity IDs are UUID hex strings (32 chars).
- Status changes go through `domain/transitions.py::validate_transition` (invalid → HTTP 409). Hierarchy integrity goes through `domain/hierarchy.py::validate_hierarchy` (invalid → HTTP 409). The domain stays I/O-free: callers fetch the parent and pass it in.
- Settings come from env with prefix `naaf_` (e.g. `naaf_db_url`).
- Commit format: `<type>: <description>` (feat/fix/refactor/docs/test/chore). One focused commit per task.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit. AAA structure, behavior-named tests. 80% coverage gate (`make coverage`).
- Work happens in the `feat/a1-control-plane` worktree at `.worktrees/a1-control-plane`.

---

## File Structure

```
naaf/
  pyproject.toml                      # uv workspace root + dev deps + pytest/ruff/mypy config
  Makefile
  docker-compose.yml                  # postgres:16
  libs/crud_router/
    pyproject.toml
    src/crud_router/
      __init__.py                     # exports Envelope, CrudRouter
      envelope.py                     # Envelope[T] model + helpers
      router.py                       # CrudRouter (sync, envelope-aware)
    tests/test_crud_router.py
  projects/server/
    pyproject.toml
    alembic.ini
    src/
      domain/
        __init__.py
        base.py                       # Entity base (id, created_at, updated_at), new_id, utcnow
        errors.py                     # RecordNotFound, IntegrityConflict, InvalidTransition, InvalidHierarchy
        work_item.py                  # WorkItem, WorkItemKind, WorkItemStatus, AcceptanceCriterion
        transitions.py                # validate_transition
        hierarchy.py                  # validate_hierarchy
        board.py                      # BoardNode, build_board_tree
        project.py                    # Project, AutonomyLevel
        team.py                       # Team, AgentDefinition, AgentRole
      adapters/
        __init__.py
        database/
          __init__.py
          ports.py                    # Repository / UnitOfWork Protocols + PaginatedResult
          orm.py                      # Base + ProjectRow, WorkItemRow, TeamRow, AgentDefinitionRow
          repository.py               # generic SqlRepository[DTO]
          repositories.py             # thin per-entity subclasses
          engine.py                   # build_engine, build_session_factory
          uow.py                      # SqlUnitOfWork
      interactors/
        __init__.py
        api/
          __init__.py
          settings.py                 # pydantic-settings Settings
          envelope_handlers.py        # exception handlers -> envelope JSON
          auth.py                     # dev-mode owner_id dependency
          deps.py                     # per-request owner-scoped UoW dependency
          schemas.py                  # Create/Update schemas per entity
          app.py                      # create_app factory
          routes/
            __init__.py
            projects.py               # projects CrudRouter
            work_items.py             # work_items router + nested/transition/board
            teams.py                  # teams + agent_definitions CrudRouters
        cli/
          __init__.py
          seed.py                     # seed default team
      migrations/
        env.py
        versions/                     # alembic revisions
    tests/
      conftest.py                     # engine + client fixtures
      domain/
        test_work_item.py
        test_transitions.py
        test_hierarchy.py
        test_board.py
        test_project.py
        test_team.py
      adapters/
        test_repository.py
        test_uow.py
        test_migrations.py
      api/
        test_app.py
        test_projects_api.py
        test_work_items_api.py
        test_teams_api.py
        test_owner_scoping.py
      cli/
        test_seed.py
  docs/ ...                           # reconciled in Task 20
```

---

### Task 1: Workspace scaffold

**Files:**
- Create: `pyproject.toml`, `Makefile`, `docker-compose.yml`
- Create: `libs/crud_router/pyproject.toml`, `libs/crud_router/src/crud_router/__init__.py`
- Create: `projects/server/pyproject.toml`, `projects/server/src/domain/__init__.py`, `projects/server/src/adapters/__init__.py`, `projects/server/src/interactors/__init__.py`
- Test: `projects/server/tests/test_smoke.py`

**Interfaces:**
- Produces: an installed `uv` workspace where `import domain`, `import adapters`, `import interactors`, and `import crud_router` all resolve; `make test`, `make coverage`, `make lint` run.

- [ ] **Step 1: Write the failing smoke test**

`projects/server/tests/test_smoke.py`:
```python
def test_workspace_packages_import():
    import domain  # noqa: F401
    import adapters  # noqa: F401
    import interactors  # noqa: F401
    import crud_router  # noqa: F401
```

- [ ] **Step 2: Create the root workspace pyproject**

`pyproject.toml`:
```toml
[project]
name = "naaf"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["projects/server", "libs/crud_router"]

[tool.uv.sources]
naaf-server = { workspace = true }
naaf-crud-router = { workspace = true }

[dependency-groups]
dev = [
    "naaf-server",
    "naaf-crud-router",
    "pytest>=8",
    "pytest-cov>=5",
    "httpx>=0.27",
    "ruff>=0.6",
    "mypy>=1.11",
]

[tool.pytest.ini_options]
testpaths = ["projects/server/tests", "libs/crud_router/tests"]
addopts = "-q"

[tool.coverage.run]
source = ["domain", "adapters", "interactors", "crud_router"]
omit = ["*/migrations/*", "*/tests/*"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
```

- [ ] **Step 3: Create the crud_router package**

`libs/crud_router/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "naaf-crud-router"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastapi>=0.115", "pydantic>=2.7"]

[tool.hatch.build.targets.wheel]
packages = ["src/crud_router"]
```

`libs/crud_router/src/crud_router/__init__.py`:
```python
"""Envelope-aware CRUD router (ported from hexrepo libs/api)."""
```

- [ ] **Step 4: Create the server package**

`projects/server/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "naaf-server"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "pydantic-settings>=2.4",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
    "naaf-crud-router",
]

[tool.uv.sources]
naaf-crud-router = { workspace = true }

[tool.hatch.build.targets.wheel]
packages = ["src/domain", "src/adapters", "src/interactors"]
```

Create empty `projects/server/src/domain/__init__.py`, `projects/server/src/adapters/__init__.py`, `projects/server/src/interactors/__init__.py`.

- [ ] **Step 5: Create the Makefile**

`Makefile`:
```makefile
.PHONY: install test coverage lint run db-upgrade db-reset

install:
	uv sync

test:
	uv run pytest

coverage:
	uv run pytest --cov --cov-report=term-missing --cov-fail-under=80

lint:
	uv run ruff check .
	uv run mypy projects/server/src libs/crud_router/src

run:
	uv run uvicorn interactors.api.app:create_app --factory --reload

db-upgrade:
	cd projects/server && uv run alembic upgrade head

db-reset:
	docker compose down -v && docker compose up -d postgres
	sleep 3
	cd projects/server && uv run alembic upgrade head
	uv run python -m interactors.cli.seed
```

- [ ] **Step 6: Create docker-compose**

`docker-compose.yml`:
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: naaf
      POSTGRES_PASSWORD: naaf
      POSTGRES_DB: naaf
    ports:
      - "5432:5432"
    volumes:
      - naaf_pg:/var/lib/postgresql/data
volumes:
  naaf_pg:
```

- [ ] **Step 7: Sync and run the smoke test**

Run: `uv sync && uv run pytest projects/server/tests/test_smoke.py -v`
Expected: PASS (all four imports resolve).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml Makefile docker-compose.yml libs projects
git commit -m "chore: scaffold uv workspace (server + crud_router)"
```

---

### Task 2: Domain base + errors

**Files:**
- Create: `projects/server/src/domain/base.py`, `projects/server/src/domain/errors.py`
- Test: `projects/server/tests/domain/test_work_item.py` (created here for the base; extended in Task 3)

**Interfaces:**
- Produces: `new_id() -> str` (32-char hex), `utcnow() -> datetime`, `Entity` base model (`id: str`, `created_at: datetime | None`, `updated_at: datetime | None`); errors `RecordNotFound`, `IntegrityConflict`, `InvalidTransition`, `InvalidHierarchy` (all subclass `DomainError`).

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/test_work_item.py`:
```python
from datetime import datetime

from domain.base import Entity, new_id, utcnow


def test_new_id_is_32_char_hex():
    value = new_id()
    assert len(value) == 32
    assert all(c in "0123456789abcdef" for c in value)


def test_utcnow_returns_datetime():
    assert isinstance(utcnow(), datetime)


def test_entity_gets_default_id():
    a = Entity()
    b = Entity()
    assert len(a.id) == 32
    assert a.id != b.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/domain/test_work_item.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.base'`

- [ ] **Step 3: Implement base + errors**

`projects/server/src/domain/base.py`:
```python
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    """A 32-char UUID hex string used for all entity IDs."""
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Entity(BaseModel):
    """Base for all domain entities. Immutable updates via model_copy."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=new_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

`projects/server/src/domain/errors.py`:
```python
class DomainError(Exception):
    """Base class for all domain-level errors."""


class RecordNotFound(DomainError):
    """A requested record does not exist (or is out of the caller's owner scope)."""


class IntegrityConflict(DomainError):
    """A persistence constraint (unique/FK) was violated."""


class InvalidTransition(DomainError):
    """A status change is not allowed by the state machine."""


class InvalidHierarchy(DomainError):
    """A work-item parent/child relationship is not allowed."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/domain/test_work_item.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/base.py projects/server/src/domain/errors.py projects/server/tests/domain/test_work_item.py
git commit -m "feat: domain base entity and error types"
```

---

### Task 3: WorkItem model + enums

**Files:**
- Create: `projects/server/src/domain/work_item.py`
- Modify: `projects/server/tests/domain/test_work_item.py` (append)

**Interfaces:**
- Consumes: `Entity`, `new_id` (Task 2).
- Produces:
  - `WorkItemKind` (str enum): `EPIC="epic"`, `FEATURE="feature"`, `TASK="task"`.
  - `WorkItemStatus` (str enum): `TO_DO="to_do"`, `IN_PROGRESS="in_progress"`, `IN_REVIEW="in_review"`, `APPROVED="approved"`, `DONE="done"`, `BLOCKED="blocked"`, `FAILED="failed"`.
  - `AcceptanceCriterion(BaseModel)`: `text: str`, `done: bool = False`.
  - `WorkItem(Entity)`: `owner_id: str`, `project_id: str`, `parent_id: str | None = None`, `kind: WorkItemKind`, `title: str`, `body: str = ""`, `acceptance_criteria: list[AcceptanceCriterion] = []`, `status: WorkItemStatus = TO_DO`.

- [ ] **Step 1: Write the failing test (append to test_work_item.py)**

```python
from domain.work_item import (
    AcceptanceCriterion,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)


def test_work_item_defaults():
    item = WorkItem(owner_id="u1", project_id="p1", kind=WorkItemKind.EPIC, title="Auth")
    assert item.status is WorkItemStatus.TO_DO
    assert item.parent_id is None
    assert item.acceptance_criteria == []
    assert len(item.id) == 32


def test_work_item_is_immutable_via_model_copy():
    item = WorkItem(owner_id="u1", project_id="p1", kind=WorkItemKind.TASK, title="x")
    updated = item.model_copy(update={"status": WorkItemStatus.IN_PROGRESS})
    assert item.status is WorkItemStatus.TO_DO  # original untouched
    assert updated.status is WorkItemStatus.IN_PROGRESS


def test_acceptance_criterion_defaults_not_done():
    crit = AcceptanceCriterion(text="returns 200")
    assert crit.done is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/domain/test_work_item.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.work_item'`

- [ ] **Step 3: Implement the model**

`projects/server/src/domain/work_item.py`:
```python
from enum import Enum

from pydantic import BaseModel, Field

from domain.base import Entity


class WorkItemKind(str, Enum):
    EPIC = "epic"
    FEATURE = "feature"
    TASK = "task"


class WorkItemStatus(str, Enum):
    TO_DO = "to_do"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class AcceptanceCriterion(BaseModel):
    text: str
    done: bool = False


class WorkItem(Entity):
    owner_id: str
    project_id: str
    parent_id: str | None = None
    kind: WorkItemKind
    title: str
    body: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    status: WorkItemStatus = WorkItemStatus.TO_DO
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/domain/test_work_item.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/work_item.py projects/server/tests/domain/test_work_item.py
git commit -m "feat: WorkItem domain model with kind and status enums"
```

---

### Task 4: Status transition state machine

**Files:**
- Create: `projects/server/src/domain/transitions.py`
- Test: `projects/server/tests/domain/test_transitions.py`

**Interfaces:**
- Consumes: `WorkItemStatus` (Task 3), `InvalidTransition` (Task 2).
- Produces: `validate_transition(current: WorkItemStatus, target: WorkItemStatus) -> WorkItemStatus` — returns `target` if allowed, else raises `InvalidTransition`. `ALLOWED_TRANSITIONS: dict[WorkItemStatus, set[WorkItemStatus]]`.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/test_transitions.py`:
```python
import pytest

from domain.errors import InvalidTransition
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus as S


def test_forward_flow_is_allowed():
    assert validate_transition(S.TO_DO, S.IN_PROGRESS) is S.IN_PROGRESS
    assert validate_transition(S.IN_PROGRESS, S.IN_REVIEW) is S.IN_REVIEW
    assert validate_transition(S.IN_REVIEW, S.APPROVED) is S.APPROVED
    assert validate_transition(S.APPROVED, S.DONE) is S.DONE


def test_review_can_bounce_back_to_in_progress():
    assert validate_transition(S.IN_REVIEW, S.IN_PROGRESS) is S.IN_PROGRESS


def test_any_active_status_can_block_and_unblock():
    assert validate_transition(S.IN_PROGRESS, S.BLOCKED) is S.BLOCKED
    assert validate_transition(S.BLOCKED, S.IN_PROGRESS) is S.IN_PROGRESS


def test_illegal_skip_raises():
    with pytest.raises(InvalidTransition):
        validate_transition(S.TO_DO, S.DONE)


def test_done_is_terminal():
    with pytest.raises(InvalidTransition):
        validate_transition(S.DONE, S.IN_PROGRESS)


def test_same_status_is_rejected():
    with pytest.raises(InvalidTransition):
        validate_transition(S.TO_DO, S.TO_DO)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/domain/test_transitions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.transitions'`

- [ ] **Step 3: Implement the state machine**

`projects/server/src/domain/transitions.py`:
```python
from domain.errors import InvalidTransition
from domain.work_item import WorkItemStatus as S

# Directed edges of the work-item lifecycle. blocked/failed are reachable from any
# active state; blocked resumes to in_progress; failed and done are terminal.
ALLOWED_TRANSITIONS: dict[S, set[S]] = {
    S.TO_DO: {S.IN_PROGRESS, S.BLOCKED, S.FAILED},
    S.IN_PROGRESS: {S.IN_REVIEW, S.BLOCKED, S.FAILED},
    S.IN_REVIEW: {S.IN_PROGRESS, S.APPROVED, S.BLOCKED, S.FAILED},
    S.APPROVED: {S.DONE, S.IN_PROGRESS, S.BLOCKED, S.FAILED},
    S.BLOCKED: {S.IN_PROGRESS, S.FAILED},
    S.DONE: set(),
    S.FAILED: set(),
}


def validate_transition(current: S, target: S) -> S:
    """Return target if the current->target edge is legal, else raise."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(
            f"Cannot transition from {current.value} to {target.value}"
        )
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/domain/test_transitions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/transitions.py projects/server/tests/domain/test_transitions.py
git commit -m "feat: work-item status transition state machine"
```

---

### Task 5: Hierarchy validation

**Files:**
- Create: `projects/server/src/domain/hierarchy.py`
- Test: `projects/server/tests/domain/test_hierarchy.py`

**Interfaces:**
- Consumes: `WorkItem`, `WorkItemKind` (Task 3), `InvalidHierarchy` (Task 2).
- Produces: `validate_hierarchy(child_kind: WorkItemKind, parent: WorkItem | None) -> None` — raises `InvalidHierarchy` on an illegal parentage. Rules: epic→parent None; feature→parent.kind epic; task→parent.kind feature.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/test_hierarchy.py`:
```python
import pytest

from domain.errors import InvalidHierarchy
from domain.hierarchy import validate_hierarchy
from domain.work_item import WorkItem, WorkItemKind as K


def _item(kind: K) -> WorkItem:
    return WorkItem(owner_id="u1", project_id="p1", kind=kind, title="x")


def test_epic_must_be_root():
    validate_hierarchy(K.EPIC, None)  # no raise


def test_epic_with_parent_is_rejected():
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.EPIC, _item(K.EPIC))


def test_feature_parent_must_be_epic():
    validate_hierarchy(K.FEATURE, _item(K.EPIC))  # no raise
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.FEATURE, None)
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.FEATURE, _item(K.FEATURE))


def test_task_parent_must_be_feature():
    validate_hierarchy(K.TASK, _item(K.FEATURE))  # no raise
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.TASK, _item(K.EPIC))
    with pytest.raises(InvalidHierarchy):
        validate_hierarchy(K.TASK, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/domain/test_hierarchy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.hierarchy'`

- [ ] **Step 3: Implement the rule**

`projects/server/src/domain/hierarchy.py`:
```python
from domain.errors import InvalidHierarchy
from domain.work_item import WorkItem, WorkItemKind as K

# Each kind's required parent kind. None means "must be a root".
REQUIRED_PARENT_KIND: dict[K, K | None] = {
    K.EPIC: None,
    K.FEATURE: K.EPIC,
    K.TASK: K.FEATURE,
}


def validate_hierarchy(child_kind: K, parent: WorkItem | None) -> None:
    """Raise InvalidHierarchy unless `parent` is a legal parent for `child_kind`.

    Pure: the caller fetches the parent (owner/project-scoped) and passes it in.
    """
    required = REQUIRED_PARENT_KIND[child_kind]
    if required is None:
        if parent is not None:
            raise InvalidHierarchy(f"{child_kind.value} must be a root (no parent)")
        return
    if parent is None:
        raise InvalidHierarchy(
            f"{child_kind.value} requires a {required.value} parent"
        )
    if parent.kind is not required:
        raise InvalidHierarchy(
            f"{child_kind.value} parent must be a {required.value}, "
            f"got {parent.kind.value}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/domain/test_hierarchy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/hierarchy.py projects/server/tests/domain/test_hierarchy.py
git commit -m "feat: work-item hierarchy validation rule"
```

---

### Task 6: Board tree builder

**Files:**
- Create: `projects/server/src/domain/board.py`
- Test: `projects/server/tests/domain/test_board.py`

**Interfaces:**
- Consumes: `WorkItem` (Task 3).
- Produces: `BoardNode(BaseModel)`: `item: WorkItem`, `children: list[BoardNode]`. `build_board_tree(items: list[WorkItem]) -> list[BoardNode]` — nests items by `parent_id`; returns roots (`parent_id is None`) with descendants attached. Orphans (parent not in set) are dropped from the tree (logged by caller, not here).

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/test_board.py`:
```python
from domain.board import build_board_tree
from domain.work_item import WorkItem, WorkItemKind as K


def _item(id_: str, kind: K, parent_id: str | None) -> WorkItem:
    return WorkItem(id=id_, owner_id="u1", project_id="p1", kind=kind,
                    title=id_, parent_id=parent_id)


def test_builds_epic_feature_task_tree():
    items = [
        _item("e", K.EPIC, None),
        _item("f", K.FEATURE, "e"),
        _item("t", K.TASK, "f"),
    ]
    roots = build_board_tree(items)
    assert len(roots) == 1
    assert roots[0].item.id == "e"
    assert roots[0].children[0].item.id == "f"
    assert roots[0].children[0].children[0].item.id == "t"


def test_multiple_roots_and_empty():
    assert build_board_tree([]) == []
    roots = build_board_tree([_item("e1", K.EPIC, None), _item("e2", K.EPIC, None)])
    assert {r.item.id for r in roots} == {"e1", "e2"}


def test_orphan_is_dropped():
    roots = build_board_tree([_item("f", K.FEATURE, "missing")])
    assert roots == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/domain/test_board.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.board'`

- [ ] **Step 3: Implement the builder**

`projects/server/src/domain/board.py`:
```python
from __future__ import annotations

from pydantic import BaseModel

from domain.work_item import WorkItem


class BoardNode(BaseModel):
    item: WorkItem
    children: list[BoardNode] = []


def build_board_tree(items: list[WorkItem]) -> list[BoardNode]:
    """Nest a flat list of work items into a parent/child forest.

    Items whose parent_id is not present in the input are dropped (not a root).
    """
    nodes: dict[str, BoardNode] = {i.id: BoardNode(item=i) for i in items}
    roots: list[BoardNode] = []
    for item in items:
        node = nodes[item.id]
        if item.parent_id is None:
            roots.append(node)
        elif item.parent_id in nodes:
            nodes[item.parent_id].children.append(node)
        # else: orphan -> dropped
    return roots
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/domain/test_board.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/board.py projects/server/tests/domain/test_board.py
git commit -m "feat: board tree builder"
```

---

### Task 7: Project model

**Files:**
- Create: `projects/server/src/domain/project.py`
- Test: `projects/server/tests/domain/test_project.py`

**Interfaces:**
- Consumes: `Entity` (Task 2).
- Produces:
  - `AutonomyLevel` (str enum): `GATED_ALL="gated_all"`, `GATED_MERGE="gated_merge"`, `FULL_AUTO="full_auto"`.
  - `Project(Entity)`: `owner_id: str`, `name: str`, `repo_url: str | None = None`, `repo_path: str | None = None`, `team_id: str | None = None`, `autonomy_level: AutonomyLevel = GATED_ALL`.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/test_project.py`:
```python
from domain.project import AutonomyLevel, Project


def test_project_defaults():
    p = Project(owner_id="u1", name="naaf")
    assert p.autonomy_level is AutonomyLevel.GATED_ALL
    assert p.repo_url is None
    assert p.team_id is None
    assert len(p.id) == 32


def test_project_immutable_update():
    p = Project(owner_id="u1", name="naaf")
    p2 = p.model_copy(update={"team_id": "t1"})
    assert p.team_id is None
    assert p2.team_id == "t1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/domain/test_project.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.project'`

- [ ] **Step 3: Implement the model**

`projects/server/src/domain/project.py`:
```python
from enum import Enum

from domain.base import Entity


class AutonomyLevel(str, Enum):
    GATED_ALL = "gated_all"
    GATED_MERGE = "gated_merge"
    FULL_AUTO = "full_auto"


class Project(Entity):
    owner_id: str
    name: str
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel = AutonomyLevel.GATED_ALL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/domain/test_project.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/project.py projects/server/tests/domain/test_project.py
git commit -m "feat: Project domain model"
```

---

### Task 8: Team + AgentDefinition models

**Files:**
- Create: `projects/server/src/domain/team.py`
- Test: `projects/server/tests/domain/test_team.py`

**Interfaces:**
- Consumes: `Entity` (Task 2).
- Produces:
  - `AgentRole` (str enum): `LEAD="lead"`, `ARCHITECT="architect"`, `BACKEND="backend"`, `FRONTEND="frontend"`, `QA="qa"`, `DEVOPS="devops"`, `CUSTOM="custom"`.
  - `AgentDefinition(Entity)`: `owner_id: str`, `team_id: str`, `role: AgentRole`, `persona_prompt: str = ""`, `model_alias: str = ""`, `runtime_adapter: str = "claude_code"`, `memory_scope: str = "project"`.
  - `Team(Entity)`: `owner_id: str`, `name: str`.

  (Team and AgentDefinition are separate tables/repos; a team's agents are queried via `team_id`, not embedded — keeps the generic repository relationship-free.)

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/test_team.py`:
```python
from domain.team import AgentDefinition, AgentRole, Team


def test_team_defaults():
    t = Team(owner_id="u1", name="Default")
    assert len(t.id) == 32


def test_agent_definition_defaults():
    a = AgentDefinition(owner_id="u1", team_id="t1", role=AgentRole.LEAD)
    assert a.runtime_adapter == "claude_code"
    assert a.memory_scope == "project"
    assert a.role is AgentRole.LEAD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/domain/test_team.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.team'`

- [ ] **Step 3: Implement the models**

`projects/server/src/domain/team.py`:
```python
from enum import Enum

from domain.base import Entity


class AgentRole(str, Enum):
    LEAD = "lead"
    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    QA = "qa"
    DEVOPS = "devops"
    CUSTOM = "custom"


class Team(Entity):
    owner_id: str
    name: str


class AgentDefinition(Entity):
    owner_id: str
    team_id: str
    role: AgentRole
    persona_prompt: str = ""
    model_alias: str = ""
    runtime_adapter: str = "claude_code"
    memory_scope: str = "project"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/domain/test_team.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/team.py projects/server/tests/domain/test_team.py
git commit -m "feat: Team and AgentDefinition domain models"
```

---

### Task 9: Envelope-aware CrudRouter (libs/crud_router)

**Files:**
- Create: `libs/crud_router/src/crud_router/envelope.py`, `libs/crud_router/src/crud_router/router.py`
- Modify: `libs/crud_router/src/crud_router/__init__.py`
- Test: `libs/crud_router/tests/test_crud_router.py`

**Interfaces:**
- Consumes: a UoW-like object exposing repositories by attribute name, each with `read(id)`, `read_multi(filters, page_size, page_number, order_by) -> PaginatedResult`, `create(dto)`, `update(id, dto)`, `delete(id)`. `PaginatedResult` here is duck-typed (`.results`, `.total`, `.page_size`, `.page_number`).
- Produces:
  - `Envelope[T](BaseModel)`: `success: bool = True`, `data: T | None = None`, `error: str | None = None`, `meta: dict | None = None`.
  - `ok(data, meta=None) -> Envelope`, `fail(error) -> Envelope`.
  - `CrudRouter(APIRouter)` — constructor `(db_dependency, repository, response_dto, create_schema, update_schema, methods, prefix=None, tags=None)`; registers enveloped `POST /` (201), `GET /{id}`, `GET /` (paginated), `PATCH /{id}`, `DELETE /{id}` (204). Overridable via `remove_api_route` + standard decorators (port of hexrepo behavior).

- [ ] **Step 1: Write the failing test**

`libs/crud_router/tests/test_crud_router.py`:
```python
from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from crud_router import CrudRouter, Envelope


class Thing(BaseModel):
    id: str
    name: str


class CreateThing(BaseModel):
    name: str


class UpdateThing(BaseModel):
    name: str | None = None


@dataclass
class Paginated:
    results: list
    total: int
    page_size: int
    page_number: int


@dataclass
class FakeRepo:
    store: dict = field(default_factory=dict)

    def create(self, dto):
        thing = Thing(id="t1", name=dto.name)
        self.store[thing.id] = thing
        return thing

    def read(self, id):
        from crud_router.errors import NotFound
        if id not in self.store:
            raise NotFound("missing")
        return self.store[id]

    def read_multi(self, filters, page_size, page_number, order_by):
        items = list(self.store.values())
        return Paginated(items, len(items), page_size, page_number)

    def update(self, id, dto):
        cur = self.store[id]
        self.store[id] = cur.model_copy(update={"name": dto.name})
        return self.store[id]

    def delete(self, id):
        self.store.pop(id, None)


class FakeUow:
    def __init__(self):
        self.things = FakeRepo()


def _client():
    uow = FakeUow()
    app = FastAPI()
    app.include_router(CrudRouter(
        db_dependency=lambda: uow,
        repository="things",
        response_dto=Thing,
        create_schema=CreateThing,
        update_schema=UpdateThing,
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/things",
    ))
    return TestClient(app)


def test_create_returns_enveloped_201():
    client = _client()
    resp = client.post("/things/", json={"name": "a"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["name"] == "a"
    assert body["error"] is None


def test_list_includes_pagination_meta():
    client = _client()
    client.post("/things/", json={"name": "a"})
    resp = client.get("/things/")
    body = resp.json()
    assert body["success"] is True
    assert body["meta"]["total"] == 1
    assert isinstance(body["data"], list)


def test_envelope_model_defaults():
    env = Envelope[str](data="x")
    assert env.success is True
    assert env.error is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest libs/crud_router/tests/test_crud_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crud_router.envelope'` / import errors

- [ ] **Step 3: Implement envelope, a local NotFound marker, and the router**

`libs/crud_router/src/crud_router/envelope.py`:
```python
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: str | None = None
    meta: dict | None = None


def ok(data, meta: dict | None = None) -> Envelope:
    return Envelope(success=True, data=data, meta=meta)


def fail(error: str) -> Envelope:
    return Envelope(success=False, data=None, error=error)
```

`libs/crud_router/src/crud_router/errors.py`:
```python
class NotFound(Exception):
    """Raised by a repository when a record is absent. Mapped to 404 by the host app."""
```

`libs/crud_router/src/crud_router/router.py`:
```python
import json
from enum import Enum
from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.types import DecoratedCallable
from pydantic import BaseModel

from crud_router.envelope import Envelope, ok


class CrudRouter(APIRouter):
    """Envelope-aware CRUD router (sync). Ported from hexrepo libs/api crud.py.

    Each handler returns an Envelope; persistence errors are NOT caught here —
    the host app registers exception handlers that emit the envelope (see
    interactors/api/envelope_handlers.py).
    """

    def __init__(
        self,
        db_dependency: Callable[[], Any],
        repository: str,
        response_dto: type[BaseModel],
        create_schema: type[BaseModel],
        update_schema: type[BaseModel],
        methods: list[str],
        prefix: str | None = None,
        tags: list[str | Enum] | None = None,
        **kwargs: Any,
    ):
        self.db_dependency = db_dependency
        self.repository = repository
        self.response_dto = response_dto
        self.create_schema = create_schema
        self.update_schema = update_schema
        self.methods = methods or ["READ"]
        super().__init__(prefix=prefix or "", tags=tags, redirect_slashes=True, **kwargs)
        self._setup_routes()

    def _repo(self, uow: Any) -> Any:
        return getattr(uow, self.repository)

    def _setup_routes(self) -> None:
        if "CREATE" in self.methods:
            self.add_api_route(
                "/", self._create(), methods=["POST"], status_code=201,
                response_model=Envelope[self.response_dto],  # type: ignore[name-defined]
            )
        if "READ" in self.methods:
            self.add_api_route(
                "/{id}", self._read(), methods=["GET"],
                response_model=Envelope[self.response_dto],  # type: ignore[name-defined]
            )
            self.add_api_route(
                "/", self._read_multi(), methods=["GET"],
                response_model=Envelope[list[self.response_dto]],  # type: ignore[name-defined]
            )
        if "UPDATE" in self.methods:
            self.add_api_route(
                "/{id}", self._update(), methods=["PATCH"],
                response_model=Envelope[self.response_dto],  # type: ignore[name-defined]
            )
        if "DELETE" in self.methods:
            self.add_api_route(
                "/{id}", self._delete(), methods=["DELETE"], status_code=204,
                response_class=Response,
            )

    def _create(self) -> Callable:
        def create_record(obj_in: self.create_schema, uow=Depends(self.db_dependency)):  # type: ignore[name-defined]
            return ok(self._repo(uow).create(obj_in))
        return create_record

    def _read(self) -> Callable:
        def read_record(id: UUID, uow=Depends(self.db_dependency)):
            return ok(self._repo(uow).read(id.hex))
        return read_record

    def _read_multi(self) -> Callable:
        def read_multiple(
            uow=Depends(self.db_dependency),
            filters: str = "{}",
            page_size: int = 50,
            page_number: int = 1,
            order_by: str = "-created_at",
        ):
            page = self._repo(uow).read_multi(
                filters=json.loads(filters),
                page_size=page_size,
                page_number=page_number,
                order_by=order_by,
            )
            return ok(page.results, meta={
                "total": page.total,
                "page_size": page.page_size,
                "page_number": page.page_number,
            })
        return read_multiple

    def _update(self) -> Callable:
        def update_record(id: UUID, obj_in: self.update_schema, uow=Depends(self.db_dependency)):  # type: ignore[name-defined]
            return ok(self._repo(uow).update(id.hex, obj_in))
        return update_record

    def _delete(self) -> Callable:
        def delete_record(id: UUID, uow=Depends(self.db_dependency)):
            self._repo(uow).delete(id.hex)
            return Response(status_code=204)
        return delete_record

    def remove_api_route(self, path: str, methods: list[str]) -> None:
        methods_ = set(methods)
        for route in list(self.routes):
            if route.path == f"{self.prefix}{path}" and route.methods == methods_:  # type: ignore[attr-defined]
                self.routes.remove(route)

    def post(self, path: str, *args: Any, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        self.remove_api_route(path, ["POST"])
        return super().post(path, *args, **kwargs)

    def get(self, path: str, *args: Any, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        self.remove_api_route(path, ["GET"])
        return super().get(path, *args, **kwargs)

    def patch(self, path: str, *args: Any, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        self.remove_api_route(path, ["PATCH"])
        return super().patch(path, *args, **kwargs)

    def delete(self, path: str, *args: Any, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        self.remove_api_route(path, ["DELETE"])
        return super().delete(path, *args, **kwargs)
```

`libs/crud_router/src/crud_router/__init__.py`:
```python
from crud_router.envelope import Envelope, fail, ok
from crud_router.errors import NotFound
from crud_router.router import CrudRouter

__all__ = ["CrudRouter", "Envelope", "NotFound", "ok", "fail"]
```

Note: the test's `read("t1")` is called with a non-UUID id from the URL only in the API tasks; in this unit test `read` is exercised through the list/create paths, and `read`/`update`/`delete` take `id.hex`. The `FakeRepo.read` test path is not hit by these three tests, so the `UUID` coercion is validated later in Task 16. (Keep this note — do not "fix" by changing FakeRepo.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest libs/crud_router/tests/test_crud_router.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add libs/crud_router
git commit -m "feat: envelope-aware CrudRouter library"
```

---

### Task 10: Persistence ports + PaginatedResult

**Files:**
- Create: `projects/server/src/adapters/database/__init__.py`, `projects/server/src/adapters/database/ports.py`
- Test: `projects/server/tests/adapters/test_repository.py` (created here; extended in Task 12)

**Interfaces:**
- Produces:
  - `PaginatedResult[DTO](BaseModel)`: `results: list[DTO]`, `total: int`, `page_size: int`, `page_number: int`.
  - `Repository(Protocol)`: `create(dto)`, `read(id: str)`, `read_multi(filters, page_size, page_number, order_by) -> PaginatedResult`, `update(id, dto)`, `delete(id)`.
  - `UnitOfWork(Protocol)`: `transaction()` contextmanager; repository properties `projects`, `work_items`, `teams`, `agent_definitions`.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/adapters/test_repository.py`:
```python
from adapters.database.ports import PaginatedResult


def test_paginated_result_shape():
    page = PaginatedResult(results=[1, 2], total=2, page_size=50, page_number=1)
    assert page.total == 2
    assert page.results == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/adapters/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.database.ports'`

- [ ] **Step 3: Implement the ports**

`projects/server/src/adapters/database/__init__.py`: (empty)

`projects/server/src/adapters/database/ports.py`:
```python
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

DTO = TypeVar("DTO", bound=BaseModel)


class PaginatedResult(BaseModel, Generic[DTO]):
    results: list[DTO]
    total: int
    page_size: int
    page_number: int


class Repository(Protocol[DTO]):
    def create(self, dto: BaseModel) -> DTO: ...
    def read(self, id: str) -> DTO: ...
    def read_multi(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str = "-created_at",
    ) -> PaginatedResult[DTO]: ...
    def update(self, id: str, dto: BaseModel) -> DTO: ...
    def delete(self, id: str) -> None: ...


class UnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager[Any]: ...

    @property
    def projects(self) -> Repository: ...
    @property
    def work_items(self) -> Repository: ...
    @property
    def teams(self) -> Repository: ...
    @property
    def agent_definitions(self) -> Repository: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/adapters/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/__init__.py projects/server/src/adapters/database/ports.py projects/server/tests/adapters/test_repository.py
git commit -m "feat: persistence ports and PaginatedResult"
```

---

### Task 11: ORM rows

**Files:**
- Create: `projects/server/src/adapters/database/orm.py`
- Test: `projects/server/tests/adapters/test_repository.py` (append)

**Interfaces:**
- Consumes: domain enums (`WorkItemKind`, `WorkItemStatus`, `AutonomyLevel`, `AgentRole`) for value storage (stored as plain strings).
- Produces: `Base` (DeclarativeBase) and rows `ProjectRow`, `WorkItemRow`, `TeamRow`, `AgentDefinitionRow`. Every row has `id` (String(32), pk, default `new_id`), `owner_id` (String, indexed, not null), `created_at`/`updated_at` (DateTime, default/onupdate `utcnow`). JSON columns: `WorkItemRow.acceptance_criteria` (JSON, default list).

- [ ] **Step 1: Write the failing test (append)**

```python
from adapters.database.orm import Base, ProjectRow, WorkItemRow


def test_orm_tables_registered():
    names = set(Base.metadata.tables.keys())
    assert {"projects", "work_items", "teams", "agent_definitions"} <= names


def test_project_row_defaults_id_and_timestamps():
    row = ProjectRow(owner_id="u1", name="naaf")
    # defaults are applied at flush, but the python-side default callables exist:
    assert ProjectRow.__table__.c.id.default is not None
    assert WorkItemRow.__table__.c.acceptance_criteria.default is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/adapters/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.database.orm'`

- [ ] **Step 3: Implement the ORM**

`projects/server/src/adapters/database/orm.py`:
```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from domain.base import new_id, utcnow


class Base(DeclarativeBase):
    pass


class _Timestamped:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class ProjectRow(_Timestamped, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    repo_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    autonomy_level: Mapped[str] = mapped_column(String(32), default="gated_all", nullable=False)


class WorkItemRow(_Timestamped, Base):
    __tablename__ = "work_items"
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), index=True, nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("work_items.id"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(String, default="", nullable=False)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="to_do", nullable=False)


class TeamRow(_Timestamped, Base):
    __tablename__ = "teams"
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class AgentDefinitionRow(_Timestamped, Base):
    __tablename__ = "agent_definitions"
    team_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("teams.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    persona_prompt: Mapped[str] = mapped_column(String, default="", nullable=False)
    model_alias: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    runtime_adapter: Mapped[str] = mapped_column(String(64), default="claude_code", nullable=False)
    memory_scope: Mapped[str] = mapped_column(String(32), default="project", nullable=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/adapters/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/orm.py projects/server/tests/adapters/test_repository.py
git commit -m "feat: SQLAlchemy ORM rows"
```

---

### Task 12: Generic SqlRepository

**Files:**
- Create: `projects/server/src/adapters/database/repository.py`
- Test: `projects/server/tests/adapters/test_repository.py` (append)

**Interfaces:**
- Consumes: `Base`, ORM rows (Task 11); `PaginatedResult` (Task 10); domain errors `RecordNotFound`, `IntegrityConflict` (Task 2).
- Produces: `SqlRepository[DTO]` with class attrs `orm_model: type[Base]`, `dto: type[BaseModel]`. Methods: `create(dto)`, `read(id)`, `read_multi(...)`, `update(id, dto)`, `delete(id)`. Constructor `(session, required_filters: dict | None)`. **Owner-scoping:** `required_filters` are applied to every query AND stamped onto every created row. Filter DSL: `__in`, `__like`, `__isnull`, `__gt`, `__gte`, `__lt`, `__lte`, `__ne`, else equality.

- [ ] **Step 1: Write the failing test (append)**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adapters.database.orm import Base, ProjectRow
from adapters.database.repository import SqlRepository
from domain.errors import RecordNotFound
from domain.project import Project


class ProjectRepo(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        yield s


def test_create_stamps_owner_and_returns_dto(session):
    repo = ProjectRepo(session, required_filters={"owner_id": "u1"})
    created = repo.create(Project(owner_id="ignored", name="naaf"))
    assert isinstance(created, Project)
    assert created.owner_id == "u1"  # stamped from required_filters
    assert len(created.id) == 32
    assert created.created_at is not None


def test_read_is_owner_scoped(session):
    ProjectRepo(session, {"owner_id": "u1"}).create(Project(owner_id="u1", name="a"))
    p = ProjectRepo(session, {"owner_id": "u1"}).read_multi().results[0]
    # another owner cannot read it
    with pytest.raises(RecordNotFound):
        ProjectRepo(session, {"owner_id": "u2"}).read(p.id)


def test_read_multi_paginates_and_counts(session):
    repo = ProjectRepo(session, {"owner_id": "u1"})
    for i in range(3):
        repo.create(Project(owner_id="u1", name=f"p{i}"))
    page = repo.read_multi(page_size=2, page_number=1)
    assert page.total == 3
    assert len(page.results) == 2


def test_filter_like(session):
    repo = ProjectRepo(session, {"owner_id": "u1"})
    repo.create(Project(owner_id="u1", name="alpha"))
    repo.create(Project(owner_id="u1", name="beta"))
    page = repo.read_multi(filters={"name__like": "alph"})
    assert page.total == 1
    assert page.results[0].name == "alpha"


def test_update_changes_fields(session):
    repo = ProjectRepo(session, {"owner_id": "u1"})
    p = repo.create(Project(owner_id="u1", name="old"))
    from domain.project import Project as P
    updated = repo.update(p.id, P(owner_id="u1", name="new"))
    assert updated.name == "new"


def test_delete_then_read_raises(session):
    repo = ProjectRepo(session, {"owner_id": "u1"})
    p = repo.create(Project(owner_id="u1", name="x"))
    repo.delete(p.id)
    with pytest.raises(RecordNotFound):
        repo.read(p.id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/adapters/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.database.repository'`

- [ ] **Step 3: Implement the generic repository**

`projects/server/src/adapters/database/repository.py`:
```python
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.exc import IntegrityError as SqlIntegrityError
from sqlalchemy.orm import Session

from adapters.database.orm import Base
from adapters.database.ports import PaginatedResult
from domain.errors import IntegrityConflict, RecordNotFound

DTO = TypeVar("DTO", bound=BaseModel)


class SqlRepository(Generic[DTO]):
    """Generic DTO-in/DTO-out repository. Subclass and set orm_model + dto."""

    orm_model: type[Base]
    dto: type[BaseModel]

    def __init__(self, session: Session, required_filters: dict[str, Any] | None = None):
        self.session = session
        self.required_filters = required_filters or {}

    # --- mapping -----------------------------------------------------------
    def _to_dto(self, row: Base) -> DTO:
        data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        return self.dto(**data)  # type: ignore[return-value]

    # --- query building ----------------------------------------------------
    def _base_select(self) -> Select:
        query = select(self.orm_model)
        for key, value in self.required_filters.items():
            query = query.where(getattr(self.orm_model, key) == value)
        return query

    def _apply_filters(self, query: Select, filters: dict[str, Any]) -> Select:
        for key, value in filters.items():
            if key.endswith("__in"):
                query = query.where(getattr(self.orm_model, key[:-4]).in_(value))
            elif key.endswith("__like"):
                query = query.where(getattr(self.orm_model, key[:-6]).ilike(f"%{value}%"))
            elif key.endswith("__isnull"):
                attr = getattr(self.orm_model, key[:-8])
                query = query.where(attr.is_(None) if value else attr.isnot(None))
            elif key.endswith("__gte"):
                query = query.where(getattr(self.orm_model, key[:-5]) >= value)
            elif key.endswith("__lte"):
                query = query.where(getattr(self.orm_model, key[:-5]) <= value)
            elif key.endswith("__gt"):
                query = query.where(getattr(self.orm_model, key[:-4]) > value)
            elif key.endswith("__lt"):
                query = query.where(getattr(self.orm_model, key[:-4]) < value)
            elif key.endswith("__ne"):
                query = query.where(getattr(self.orm_model, key[:-4]) != value)
            else:
                query = query.where(getattr(self.orm_model, key) == value)
        return query

    def _order(self, query: Select, order_by: str | None) -> Select:
        if not order_by:
            return query
        direction = desc if order_by.startswith("-") else asc
        return query.order_by(direction(order_by.lstrip("-")))

    def _get_one_row(self, id: str) -> Base:
        query = self._base_select().where(self.orm_model.id == id)
        row = self.session.execute(query).scalar_one_or_none()
        if row is None:
            raise RecordNotFound(f"{self.orm_model.__name__} {id} not found")
        return row

    # --- CRUD --------------------------------------------------------------
    def create(self, dto: BaseModel) -> DTO:
        data = {k: v for k, v in dto.model_dump().items() if v is not None}
        data.update(self.required_filters)  # stamp owner_id (and any scope)
        row = self.orm_model(**data)
        self.session.add(row)
        try:
            self.session.flush()
        except SqlIntegrityError as err:
            self.session.rollback()
            raise IntegrityConflict(str(err.orig)) from err
        self.session.refresh(row)
        return self._to_dto(row)

    def read(self, id: str) -> DTO:
        return self._to_dto(self._get_one_row(id))

    def read_multi(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str = "-created_at",
    ) -> PaginatedResult[DTO]:
        filters = filters or {}
        query = self._apply_filters(self._base_select(), filters)
        query = self._order(query, order_by)

        count_query = self._apply_filters(
            select(func.count()).select_from(self.orm_model), filters
        )
        for key, value in self.required_filters.items():
            count_query = count_query.where(getattr(self.orm_model, key) == value)
        total = int(self.session.execute(count_query).scalar_one())

        if page_size > 0 and page_number >= 1:
            query = query.offset((page_number - 1) * page_size).limit(page_size)
        rows = self.session.execute(query).scalars().all()
        return PaginatedResult[self.dto](  # type: ignore[name-defined]
            results=[self._to_dto(r) for r in rows],
            total=total,
            page_size=page_size,
            page_number=page_number,
        )

    def update(self, id: str, dto: BaseModel) -> DTO:
        row = self._get_one_row(id)
        for key, value in dto.model_dump(exclude_unset=True).items():
            if key in ("id", "owner_id", "created_at"):
                continue
            setattr(row, key, value)
        try:
            self.session.flush()
        except SqlIntegrityError as err:
            self.session.rollback()
            raise IntegrityConflict(str(err.orig)) from err
        self.session.refresh(row)
        return self._to_dto(row)

    def delete(self, id: str) -> None:
        row = self._get_one_row(id)
        self.session.delete(row)
        self.session.flush()
```

Note on the count query: `_base_select` adds required filters to the SELECT, but the count
query is built separately, so required filters are re-applied to it explicitly (the loop after
`count_query`). Do not remove that loop — without it, totals would ignore owner scoping.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/adapters/test_repository.py -v`
Expected: PASS (all repository tests)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/repository.py projects/server/tests/adapters/test_repository.py
git commit -m "feat: generic owner-scoped SqlRepository"
```

---

### Task 13: Per-entity repositories, engine, UnitOfWork

**Files:**
- Create: `projects/server/src/adapters/database/repositories.py`, `projects/server/src/adapters/database/engine.py`, `projects/server/src/adapters/database/uow.py`
- Test: `projects/server/tests/adapters/test_uow.py`

**Interfaces:**
- Consumes: `SqlRepository` (Task 12); ORM rows (Task 11); domain DTOs.
- Produces:
  - `repositories.py`: `ProjectRepository`, `WorkItemRepository`, `TeamRepository`, `AgentDefinitionRepository` (each sets `orm_model` + `dto`).
  - `engine.py`: `build_engine(db_url: str) -> Engine`, `build_session_factory(engine) -> sessionmaker`.
  - `uow.py`: `SqlUnitOfWork(session_factory, required_filters)`: `transaction()` contextmanager (commit on success, rollback on error); cached repo properties `projects`, `work_items`, `teams`, `agent_definitions`; `session` property.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/adapters/test_uow.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.work_item import WorkItem, WorkItemKind


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _uow(factory):
    return SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})


def test_transaction_commits_multiple_writes_atomically(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        proj = uow.projects.create(Project(owner_id="u1", name="naaf"))
        uow.work_items.create(
            WorkItem(owner_id="u1", project_id=proj.id, kind=WorkItemKind.EPIC, title="Auth")
        )
    uow2 = _uow(session_factory)
    assert uow2.projects.read_multi().total == 1
    assert uow2.work_items.read_multi().total == 1


def test_transaction_rolls_back_on_error(session_factory):
    uow = _uow(session_factory)
    with pytest.raises(RuntimeError):
        with uow.transaction():
            uow.projects.create(Project(owner_id="u1", name="naaf"))
            raise RuntimeError("boom")
    uow2 = _uow(session_factory)
    assert uow2.projects.read_multi().total == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/adapters/test_uow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.database.uow'`

- [ ] **Step 3: Implement repositories, engine, uow**

`projects/server/src/adapters/database/repositories.py`:
```python
from adapters.database.orm import (
    AgentDefinitionRow,
    ProjectRow,
    TeamRow,
    WorkItemRow,
)
from adapters.database.repository import SqlRepository
from domain.project import Project
from domain.team import AgentDefinition, Team
from domain.work_item import WorkItem


class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


class WorkItemRepository(SqlRepository[WorkItem]):
    orm_model = WorkItemRow
    dto = WorkItem


class TeamRepository(SqlRepository[Team]):
    orm_model = TeamRow
    dto = Team


class AgentDefinitionRepository(SqlRepository[AgentDefinition]):
    orm_model = AgentDefinitionRow
    dto = AgentDefinition
```

`projects/server/src/adapters/database/engine.py`:
```python
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker


def build_engine(db_url: str) -> Engine:
    return create_engine(db_url, future=True)


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
```

`projects/server/src/adapters/database/uow.py`:
```python
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy.orm import Session, sessionmaker

from adapters.database.repositories import (
    AgentDefinitionRepository,
    ProjectRepository,
    TeamRepository,
    WorkItemRepository,
)


class SqlUnitOfWork:
    """Owns one session + transaction boundary. Repositories share that session
    and apply required_filters for owner-scoping."""

    def __init__(self, session_factory: sessionmaker, required_filters: dict[str, Any] | None = None):
        self._session_factory = session_factory
        self._required_filters = required_filters or {}
        self._session: Session | None = None
        self._repos: dict[str, Any] = {}

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    @contextmanager
    def transaction(self) -> Iterator["SqlUnitOfWork"]:
        session = self.session
        try:
            yield self
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            self._session = None
            self._repos = {}

    def _repo(self, name: str, cls: type) -> Any:
        if name not in self._repos:
            self._repos[name] = cls(self.session, required_filters=self._required_filters)
        return self._repos[name]

    @property
    def projects(self) -> ProjectRepository:
        return self._repo("projects", ProjectRepository)

    @property
    def work_items(self) -> WorkItemRepository:
        return self._repo("work_items", WorkItemRepository)

    @property
    def teams(self) -> TeamRepository:
        return self._repo("teams", TeamRepository)

    @property
    def agent_definitions(self) -> AgentDefinitionRepository:
        return self._repo("agent_definitions", AgentDefinitionRepository)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/adapters/test_uow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/repositories.py projects/server/src/adapters/database/engine.py projects/server/src/adapters/database/uow.py projects/server/tests/adapters/test_uow.py
git commit -m "feat: per-entity repositories, engine, and SqlUnitOfWork"
```

---

### Task 14: Alembic baseline migration

**Files:**
- Create: `projects/server/alembic.ini`, `projects/server/src/migrations/env.py`, `projects/server/src/migrations/script.py.mako`, `projects/server/src/migrations/versions/0001_initial.py`
- Test: `projects/server/tests/adapters/test_migrations.py`

**Interfaces:**
- Produces: a runnable Alembic config whose `target_metadata` is `Base.metadata`; an initial migration creating all four tables. `make db-upgrade` applies it on Postgres.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/adapters/test_migrations.py`:
```python
import subprocess
from pathlib import Path


def test_alembic_upgrade_head_on_sqlite(tmp_path):
    db_file = tmp_path / "naaf.db"
    server_dir = Path(__file__).resolve().parents[2]  # projects/server
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=server_dir,
        env={"naaf_db_url": f"sqlite:///{db_file}", "PATH": __import__("os").environ["PATH"]},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # tables exist
    import sqlite3
    con = sqlite3.connect(db_file)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"projects", "work_items", "teams", "agent_definitions"} <= tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/adapters/test_migrations.py -v`
Expected: FAIL (alembic not configured; returncode != 0)

- [ ] **Step 3: Create alembic config + env + migration**

`projects/server/alembic.ini` (minimal):
```ini
[alembic]
script_location = src/migrations
prepend_sys_path = src

[loggers]
keys = root
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
qualname =
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`projects/server/src/migrations/env.py`:
```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from adapters.database.orm import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", os.environ["naaf_db_url"])
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`projects/server/src/migrations/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Generate the initial revision (this writes `versions/0001_initial.py`):
```bash
cd projects/server
naaf_db_url="sqlite:////tmp/naaf_gen.db" uv run alembic revision --autogenerate -m "initial" --rev-id 0001_initial
```
Review the generated file: it must `op.create_table` for `projects`, `work_items` (with the
self-FK on `parent_id` and FK on `project_id`), `teams`, `agent_definitions`. If autogenerate
misses the JSON column type, set it to `sa.JSON()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/adapters/test_migrations.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/alembic.ini projects/server/src/migrations
git commit -m "feat: alembic baseline migration"
```

---

### Task 15: API foundation — settings, auth, deps, handlers, app factory

**Files:**
- Create: `projects/server/src/interactors/api/__init__.py`, `settings.py`, `envelope_handlers.py`, `auth.py`, `deps.py`, `app.py`
- Create: `projects/server/tests/conftest.py`, `projects/server/tests/api/test_app.py`

**Interfaces:**
- Consumes: `build_engine`, `build_session_factory` (Task 13); `SqlUnitOfWork` (Task 13); domain errors (Task 2); `Envelope` (Task 9).
- Produces:
  - `Settings(BaseSettings)`: `db_url: str = "sqlite://"`, `auth_mode: str = "dev"`, `dev_owner_id: str = "dev-user"`; env prefix `naaf_`.
  - `get_owner_id(request) -> str` (dev mode → settings.dev_owner_id).
  - `get_uow(request, owner_id)` dependency: yields an owner-scoped `SqlUnitOfWork` inside an open `transaction()`.
  - `create_app(settings=None, session_factory=None) -> FastAPI`: builds engine/session_factory (unless injected), stores `session_factory` on `app.state`, registers exception handlers + routers, exposes `GET /health`.

- [ ] **Step 1: Write the failing test + conftest**

`projects/server/tests/conftest.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from adapters.database.orm import Base
from interactors.api.app import create_app
from interactors.api.settings import Settings


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(session_factory):
    app = create_app(settings=Settings(), session_factory=session_factory)
    return TestClient(app)
```

`projects/server/tests/api/test_app.py`:
```python
def test_health_is_enveloped_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"success": True, "data": {"status": "ok"}, "error": None, "meta": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/api/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'interactors.api.app'`

- [ ] **Step 3: Implement the API foundation**

`projects/server/src/interactors/api/__init__.py`: (empty)

`projects/server/src/interactors/api/settings.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="naaf_")

    db_url: str = "sqlite://"
    auth_mode: str = "dev"
    dev_owner_id: str = "dev-user"
```

`projects/server/src/interactors/api/auth.py`:
```python
from fastapi import Request


def get_owner_id(request: Request) -> str:
    """Dev auth: every request is attributed to the configured dev owner.
    Auth0 integration (remote profile) plugs in here later."""
    settings = request.app.state.settings
    if settings.auth_mode == "dev":
        return settings.dev_owner_id
    raise NotImplementedError(f"auth_mode {settings.auth_mode} not supported in A1")
```

`projects/server/src/interactors/api/deps.py`:
```python
from typing import Iterator

from fastapi import Depends, Request

from adapters.database.uow import SqlUnitOfWork
from interactors.api.auth import get_owner_id


def get_uow(request: Request, owner_id: str = Depends(get_owner_id)) -> Iterator[SqlUnitOfWork]:
    uow = SqlUnitOfWork(
        request.app.state.session_factory,
        required_filters={"owner_id": owner_id},
    )
    with uow.transaction():
        yield uow
```

`projects/server/src/interactors/api/envelope_handlers.py`:
```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from domain.errors import (
    IntegrityConflict,
    InvalidHierarchy,
    InvalidTransition,
    RecordNotFound,
)


def _envelope(status_code: int, error: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None, "error": error, "meta": None},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RecordNotFound)
    async def _not_found(_: Request, exc: RecordNotFound):
        return _envelope(404, str(exc))

    @app.exception_handler(IntegrityConflict)
    async def _conflict(_: Request, exc: IntegrityConflict):
        return _envelope(409, str(exc))

    @app.exception_handler(InvalidTransition)
    async def _bad_transition(_: Request, exc: InvalidTransition):
        return _envelope(409, str(exc))

    @app.exception_handler(InvalidHierarchy)
    async def _bad_hierarchy(_: Request, exc: InvalidHierarchy):
        return _envelope(409, str(exc))

    @app.exception_handler(ValidationError)
    async def _domain_validation(_: Request, exc: ValidationError):
        return _envelope(422, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError):
        return _envelope(422, str(exc))
```

`projects/server/src/interactors/api/app.py`:
```python
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from adapters.database.engine import build_engine, build_session_factory
from crud_router import ok
from interactors.api.envelope_handlers import register_exception_handlers
from interactors.api.routes import register_routers
from interactors.api.settings import Settings


def create_app(settings: Settings | None = None, session_factory: sessionmaker | None = None) -> FastAPI:
    settings = settings or Settings()
    if session_factory is None:
        engine = build_engine(settings.db_url)
        session_factory = build_session_factory(engine)

    app = FastAPI(title="NAAF Control Plane")
    app.state.settings = settings
    app.state.session_factory = session_factory

    register_exception_handlers(app)
    register_routers(app)

    @app.get("/health")
    def health():
        return ok({"status": "ok"})

    return app
```

Create a placeholder `projects/server/src/interactors/api/routes/__init__.py` so the import in
`app.py` resolves (real routers are added in Tasks 16–18):
```python
from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/api/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api projects/server/tests/conftest.py projects/server/tests/api/test_app.py
git commit -m "feat: API foundation (settings, auth, deps, handlers, app factory)"
```

---

### Task 16: Project routes + schemas

**Files:**
- Create: `projects/server/src/interactors/api/schemas.py`, `projects/server/src/interactors/api/routes/projects.py`
- Modify: `projects/server/src/interactors/api/routes/__init__.py`
- Test: `projects/server/tests/api/test_projects_api.py`, `projects/server/tests/api/test_owner_scoping.py`

**Interfaces:**
- Consumes: `CrudRouter` (Task 9); `get_uow` (Task 15); `Project` (Task 7).
- Produces:
  - `schemas.py`: `CreateProject(name, repo_url=None, repo_path=None, team_id=None, autonomy_level=GATED_ALL)`; `UpdateProject(name=None, repo_url=None, repo_path=None, team_id=None, autonomy_level=None)`. (No `owner_id` — stamped by the repo.)
  - `routes/projects.py`: `build_projects_router(db_dependency) -> CrudRouter` for `/projects` with all four methods.

- [ ] **Step 1: Write the failing tests**

`projects/server/tests/api/test_projects_api.py`:
```python
def test_create_and_get_project(client):
    created = client.post("/projects/", json={"name": "naaf"}).json()
    assert created["success"] is True
    pid = created["data"]["id"]
    assert created["data"]["owner_id"] == "dev-user"  # stamped

    got = client.get(f"/projects/{pid}").json()
    assert got["data"]["name"] == "naaf"


def test_list_projects_has_meta(client):
    client.post("/projects/", json={"name": "a"})
    client.post("/projects/", json={"name": "b"})
    body = client.get("/projects/").json()
    assert body["meta"]["total"] == 2
    assert len(body["data"]) == 2


def test_patch_project(client):
    pid = client.post("/projects/", json={"name": "old"}).json()["data"]["id"]
    body = client.patch(f"/projects/{pid}", json={"name": "new"}).json()
    assert body["data"]["name"] == "new"


def test_delete_project(client):
    pid = client.post("/projects/", json={"name": "x"}).json()["data"]["id"]
    assert client.delete(f"/projects/{pid}").status_code == 204
    assert client.get(f"/projects/{pid}").status_code == 404


def test_get_missing_project_is_enveloped_404(client):
    resp = client.get("/projects/" + "0" * 32)
    assert resp.status_code == 404
    assert resp.json()["success"] is False
```

`projects/server/tests/api/test_owner_scoping.py`:
```python
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def test_other_owner_cannot_read_project(session_factory):
    app_u1 = create_app(settings=Settings(dev_owner_id="u1"), session_factory=session_factory)
    app_u2 = create_app(settings=Settings(dev_owner_id="u2"), session_factory=session_factory)
    pid = TestClient(app_u1).post("/projects/", json={"name": "secret"}).json()["data"]["id"]
    # u2 shares the DB but is scoped out -> 404
    assert TestClient(app_u2).get(f"/projects/{pid}").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/api/test_projects_api.py -v`
Expected: FAIL (routes not registered → 404 on POST `/projects/`, or import error)

- [ ] **Step 3: Implement schemas + project router + registration**

`projects/server/src/interactors/api/schemas.py`:
```python
from pydantic import BaseModel

from domain.project import AutonomyLevel
from domain.work_item import AcceptanceCriterion, WorkItemKind, WorkItemStatus
from domain.team import AgentRole


class CreateProject(BaseModel):
    name: str
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel = AutonomyLevel.GATED_ALL


class UpdateProject(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel | None = None


class CreateWorkItem(BaseModel):
    kind: WorkItemKind
    title: str
    body: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = []
    parent_id: str | None = None


class UpdateWorkItem(BaseModel):
    title: str | None = None
    body: str | None = None
    acceptance_criteria: list[AcceptanceCriterion] | None = None
    # NOTE: status is intentionally absent — status changes go through the
    # transition route so the state machine is always enforced.


class TransitionRequest(BaseModel):
    status: WorkItemStatus


class CreateTeam(BaseModel):
    name: str


class UpdateTeam(BaseModel):
    name: str | None = None


class CreateAgentDefinition(BaseModel):
    team_id: str
    role: AgentRole
    persona_prompt: str = ""
    model_alias: str = ""
    runtime_adapter: str = "claude_code"
    memory_scope: str = "project"


class UpdateAgentDefinition(BaseModel):
    role: AgentRole | None = None
    persona_prompt: str | None = None
    model_alias: str | None = None
    runtime_adapter: str | None = None
    memory_scope: str | None = None
```

`projects/server/src/interactors/api/routes/projects.py`:
```python
from typing import Callable

from crud_router import CrudRouter

from domain.project import Project
from interactors.api.schemas import CreateProject, UpdateProject


def build_projects_router(db_dependency: Callable) -> CrudRouter:
    return CrudRouter(
        db_dependency=db_dependency,
        repository="projects",
        response_dto=Project,
        create_schema=CreateProject,
        update_schema=UpdateProject,
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/projects",
        tags=["projects"],
    )
```

`projects/server/src/interactors/api/routes/__init__.py` (replace placeholder):
```python
from fastapi import FastAPI

from interactors.api.deps import get_uow
from interactors.api.routes.projects import build_projects_router


def register_routers(app: FastAPI) -> None:
    app.include_router(build_projects_router(get_uow))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest projects/server/tests/api/test_projects_api.py projects/server/tests/api/test_owner_scoping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/schemas.py projects/server/src/interactors/api/routes/projects.py projects/server/src/interactors/api/routes/__init__.py projects/server/tests/api/test_projects_api.py projects/server/tests/api/test_owner_scoping.py
git commit -m "feat: project CRUD routes with owner scoping"
```

---

### Task 17: WorkItem routes — nested create, transition, board

**Files:**
- Create: `projects/server/src/interactors/api/routes/work_items.py`
- Modify: `projects/server/src/interactors/api/routes/__init__.py`
- Test: `projects/server/tests/api/test_work_items_api.py`

**Interfaces:**
- Consumes: `CrudRouter` (Task 9); `get_uow` (Task 15); `validate_hierarchy` (Task 5); `validate_transition` (Task 4); `build_board_tree`, `BoardNode` (Task 6); schemas `CreateWorkItem`, `UpdateWorkItem`, `TransitionRequest` (Task 16); `WorkItem`, `WorkItemStatus` (Task 3); `Envelope`, `ok` (Task 9).
- Produces **two** router builders (a `CrudRouter` carries a single `prefix`, so the
  `/work-items`-prefixed routes and the `/projects/...`-nested routes must live on separate
  routers):
  - `build_work_items_router(db_dependency) -> CrudRouter` (prefix `/work-items`): generic
    `GET /work-items/{id}`, `GET /work-items/` (list), `PATCH /work-items/{id}`,
    `DELETE /work-items/{id}` (**no generic CREATE**), plus a hand-written
    `POST /work-items/{id}/transition` registered as the prefix-relative path `/{id}/transition`.
  - `build_project_work_items_router(db_dependency) -> APIRouter` (no prefix): the
    `/projects/{project_id}`-scoped routes — `POST /projects/{project_id}/work-items` (nested
    create: fetch parent if `parent_id`, `validate_hierarchy`, enforce same-project parent, set
    `project_id`) and `GET /projects/{project_id}/board` (`build_board_tree`).

- [ ] **Step 1: Write the failing tests**

`projects/server/tests/api/test_work_items_api.py`:
```python
def _project(client) -> str:
    return client.post("/projects/", json={"name": "naaf"}).json()["data"]["id"]


def test_nested_create_epic_then_feature_then_task(client):
    pid = _project(client)
    epic = client.post(f"/projects/{pid}/work-items",
                       json={"kind": "epic", "title": "Auth"}).json()["data"]
    assert epic["project_id"] == pid
    assert epic["owner_id"] == "dev-user"

    feat = client.post(f"/projects/{pid}/work-items",
                       json={"kind": "feature", "title": "Login", "parent_id": epic["id"]})
    assert feat.status_code == 201
    fid = feat.json()["data"]["id"]

    task = client.post(f"/projects/{pid}/work-items",
                       json={"kind": "task", "title": "Form", "parent_id": fid})
    assert task.status_code == 201


def test_feature_without_epic_parent_is_409(client):
    pid = _project(client)
    resp = client.post(f"/projects/{pid}/work-items",
                       json={"kind": "feature", "title": "x"})
    assert resp.status_code == 409
    assert resp.json()["success"] is False


def test_transition_to_do_to_in_progress(client):
    pid = _project(client)
    wid = client.post(f"/projects/{pid}/work-items",
                      json={"kind": "epic", "title": "x"}).json()["data"]["id"]
    body = client.post(f"/work-items/{wid}/transition",
                       json={"status": "in_progress"}).json()
    assert body["data"]["status"] == "in_progress"


def test_illegal_transition_is_409(client):
    pid = _project(client)
    wid = client.post(f"/projects/{pid}/work-items",
                      json={"kind": "epic", "title": "x"}).json()["data"]["id"]
    resp = client.post(f"/work-items/{wid}/transition", json={"status": "done"})
    assert resp.status_code == 409


def test_board_returns_nested_tree(client):
    pid = _project(client)
    epic = client.post(f"/projects/{pid}/work-items",
                       json={"kind": "epic", "title": "E"}).json()["data"]
    client.post(f"/projects/{pid}/work-items",
                json={"kind": "feature", "title": "F", "parent_id": epic["id"]})
    board = client.get(f"/projects/{pid}/board").json()
    assert board["success"] is True
    assert len(board["data"]) == 1
    assert board["data"][0]["item"]["id"] == epic["id"]
    assert board["data"][0]["children"][0]["item"]["title"] == "F"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/api/test_work_items_api.py -v`
Expected: FAIL (routes not registered)

- [ ] **Step 3: Implement the work-items router**

`projects/server/src/interactors/api/routes/work_items.py`:
```python
from typing import Callable

from fastapi import APIRouter, Depends

from crud_router import CrudRouter, Envelope, ok

from adapters.database.uow import SqlUnitOfWork
from domain.board import BoardNode, build_board_tree
from domain.errors import InvalidHierarchy
from domain.hierarchy import validate_hierarchy
from domain.transitions import validate_transition
from domain.work_item import WorkItem
from interactors.api.schemas import CreateWorkItem, TransitionRequest, UpdateWorkItem


def build_work_items_router(db_dependency: Callable) -> CrudRouter:
    """Prefix /work-items: generic READ/UPDATE/DELETE (no CREATE) + transition.
    Paths added here are relative to the prefix."""
    router = CrudRouter(
        db_dependency=db_dependency,
        repository="work_items",
        response_dto=WorkItem,
        create_schema=CreateWorkItem,
        update_schema=UpdateWorkItem,
        methods=["READ", "UPDATE", "DELETE"],  # no generic CREATE
        prefix="/work-items",
        tags=["work-items"],
    )

    @router.post("/{id}/transition", response_model=Envelope[WorkItem])
    def transition_work_item(
        id: str,
        body: TransitionRequest,
        uow: SqlUnitOfWork = Depends(db_dependency),
    ):
        current = uow.work_items.read(id)
        new_status = validate_transition(current.status, body.status)
        updated = current.model_copy(update={"status": new_status})
        return ok(uow.work_items.update(id, updated))

    return router


def build_project_work_items_router(db_dependency: Callable) -> APIRouter:
    """No prefix: the /projects/{project_id}-scoped nested-create and board routes."""
    router = APIRouter(tags=["work-items"])

    @router.post("/projects/{project_id}/work-items", status_code=201,
                 response_model=Envelope[WorkItem])
    def create_work_item(
        project_id: str,
        body: CreateWorkItem,
        uow: SqlUnitOfWork = Depends(db_dependency),
    ):
        parent = uow.work_items.read(body.parent_id) if body.parent_id else None
        validate_hierarchy(body.kind, parent)
        if parent is not None and parent.project_id != project_id:
            raise InvalidHierarchy("parent must belong to the same project")
        item = WorkItem(
            owner_id="",  # stamped by repo from required_filters
            project_id=project_id,
            parent_id=body.parent_id,
            kind=body.kind,
            title=body.title,
            body=body.body,
            acceptance_criteria=body.acceptance_criteria,
        )
        return ok(uow.work_items.create(item))

    @router.get("/projects/{project_id}/board", response_model=Envelope[list[BoardNode]])
    def board(project_id: str, uow: SqlUnitOfWork = Depends(db_dependency)):
        page = uow.work_items.read_multi(
            filters={"project_id": project_id}, page_size=0, order_by="created_at"
        )
        return ok(build_board_tree(page.results))

    return router
```

Note: `read_multi(page_size=0)` returns all rows (the repository skips offset/limit when
`page_size <= 0`). The transition route calls `update(id, updated)` with the **full** WorkItem
DTO; the repository's `update` skips `id`/`owner_id`/`created_at` and persists `status`
(and re-sets `updated_at` via the ORM `onupdate`). Generic `GET /work-items/{id}` is provided by
the CrudRouter READ method — no custom read route is needed.

`projects/server/src/interactors/api/routes/__init__.py` (add both routers):
```python
from fastapi import FastAPI

from interactors.api.deps import get_uow
from interactors.api.routes.projects import build_projects_router
from interactors.api.routes.work_items import (
    build_project_work_items_router,
    build_work_items_router,
)


def register_routers(app: FastAPI) -> None:
    app.include_router(build_projects_router(get_uow))
    app.include_router(build_work_items_router(get_uow))
    app.include_router(build_project_work_items_router(get_uow))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/api/test_work_items_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/routes/work_items.py projects/server/src/interactors/api/routes/__init__.py projects/server/tests/api/test_work_items_api.py
git commit -m "feat: work-item nested create, transition, and board routes"
```

---

### Task 18: Team + AgentDefinition routes

**Files:**
- Create: `projects/server/src/interactors/api/routes/teams.py`
- Modify: `projects/server/src/interactors/api/routes/__init__.py`
- Test: `projects/server/tests/api/test_teams_api.py`

**Interfaces:**
- Consumes: `CrudRouter` (Task 9); schemas `CreateTeam`/`UpdateTeam`/`CreateAgentDefinition`/`UpdateAgentDefinition` (Task 16); `Team`, `AgentDefinition` (Task 8).
- Produces: `build_teams_router(db)` (`/teams`, all methods) and `build_agent_definitions_router(db)` (`/agent-definitions`, all methods).

- [ ] **Step 1: Write the failing test**

`projects/server/tests/api/test_teams_api.py`:
```python
def test_create_team_and_agent_definition(client):
    team = client.post("/teams/", json={"name": "Default"}).json()["data"]
    assert team["owner_id"] == "dev-user"

    agent = client.post("/agent-definitions/", json={
        "team_id": team["id"], "role": "lead"
    }).json()["data"]
    assert agent["role"] == "lead"
    assert agent["runtime_adapter"] == "claude_code"


def test_list_agent_definitions_filtered_by_team(client):
    t = client.post("/teams/", json={"name": "T"}).json()["data"]["id"]
    client.post("/agent-definitions/", json={"team_id": t, "role": "lead"})
    client.post("/agent-definitions/", json={"team_id": t, "role": "qa"})
    body = client.get(f'/agent-definitions/?filters={{"team_id":"{t}"}}').json()
    assert body["meta"]["total"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/api/test_teams_api.py -v`
Expected: FAIL (routes not registered)

- [ ] **Step 3: Implement the routers + registration**

`projects/server/src/interactors/api/routes/teams.py`:
```python
from typing import Callable

from crud_router import CrudRouter

from domain.team import AgentDefinition, Team
from interactors.api.schemas import (
    CreateAgentDefinition,
    CreateTeam,
    UpdateAgentDefinition,
    UpdateTeam,
)


def build_teams_router(db_dependency: Callable) -> CrudRouter:
    return CrudRouter(
        db_dependency=db_dependency,
        repository="teams",
        response_dto=Team,
        create_schema=CreateTeam,
        update_schema=UpdateTeam,
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/teams",
        tags=["teams"],
    )


def build_agent_definitions_router(db_dependency: Callable) -> CrudRouter:
    return CrudRouter(
        db_dependency=db_dependency,
        repository="agent_definitions",
        response_dto=AgentDefinition,
        create_schema=CreateAgentDefinition,
        update_schema=UpdateAgentDefinition,
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/agent-definitions",
        tags=["agent-definitions"],
    )
```

`projects/server/src/interactors/api/routes/__init__.py` (final form):
```python
from fastapi import FastAPI

from interactors.api.deps import get_uow
from interactors.api.routes.projects import build_projects_router
from interactors.api.routes.teams import (
    build_agent_definitions_router,
    build_teams_router,
)
from interactors.api.routes.work_items import (
    build_project_work_items_router,
    build_work_items_router,
)


def register_routers(app: FastAPI) -> None:
    app.include_router(build_projects_router(get_uow))
    app.include_router(build_work_items_router(get_uow))
    app.include_router(build_project_work_items_router(get_uow))
    app.include_router(build_teams_router(get_uow))
    app.include_router(build_agent_definitions_router(get_uow))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/api/test_teams_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/routes/teams.py projects/server/src/interactors/api/routes/__init__.py projects/server/tests/api/test_teams_api.py
git commit -m "feat: team and agent-definition CRUD routes"
```

---

### Task 19: CLI seed (default team)

**Files:**
- Create: `projects/server/src/interactors/cli/__init__.py`, `projects/server/src/interactors/cli/seed.py`
- Test: `projects/server/tests/cli/test_seed.py`

**Interfaces:**
- Consumes: `SqlUnitOfWork` (Task 13); `Team`, `AgentDefinition`, `AgentRole` (Task 8).
- Produces: `seed_default_team(session_factory, owner_id: str) -> str` — creates a team "Default Team" with lead/backend/qa agents (idempotent: skips if a team named "Default Team" already exists for the owner). Returns the team id. `main()` reads `Settings` and runs it.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/cli/test_seed.py`:
```python
from interactors.cli.seed import seed_default_team


def test_seed_creates_team_with_three_agents(session_factory):
    team_id = seed_default_team(session_factory, owner_id="u1")

    from adapters.database.uow import SqlUnitOfWork
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        teams = uow.teams.read_multi().results
        agents = uow.agent_definitions.read_multi(filters={"team_id": team_id}).results
    assert len(teams) == 1
    assert {a.role.value for a in agents} == {"lead", "backend", "qa"}


def test_seed_is_idempotent(session_factory):
    seed_default_team(session_factory, owner_id="u1")
    seed_default_team(session_factory, owner_id="u1")
    from adapters.database.uow import SqlUnitOfWork
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        assert uow.teams.read_multi().total == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest projects/server/tests/cli/test_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'interactors.cli.seed'`

- [ ] **Step 3: Implement the seed**

`projects/server/src/interactors/cli/__init__.py`: (empty)

`projects/server/src/interactors/cli/seed.py`:
```python
from sqlalchemy.orm import sessionmaker

from adapters.database.engine import build_engine, build_session_factory
from adapters.database.uow import SqlUnitOfWork
from domain.team import AgentDefinition, AgentRole, Team
from interactors.api.settings import Settings

DEFAULT_TEAM_NAME = "Default Team"
DEFAULT_ROLES = [AgentRole.LEAD, AgentRole.BACKEND, AgentRole.QA]


def seed_default_team(session_factory: sessionmaker, owner_id: str) -> str:
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner_id})
    with uow.transaction():
        existing = uow.teams.read_multi(filters={"name": DEFAULT_TEAM_NAME})
        if existing.total:
            return existing.results[0].id
        team = uow.teams.create(Team(owner_id=owner_id, name=DEFAULT_TEAM_NAME))
        for role in DEFAULT_ROLES:
            uow.agent_definitions.create(
                AgentDefinition(owner_id=owner_id, team_id=team.id, role=role)
            )
        return team.id


def main() -> None:
    settings = Settings()
    engine = build_engine(settings.db_url)
    seed_default_team(build_session_factory(engine), owner_id=settings.dev_owner_id)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest projects/server/tests/cli/test_seed.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/cli projects/server/tests/cli/test_seed.py
git commit -m "feat: CLI seed for the default team"
```

---

### Task 20: Reconcile docs + ADR-0001 + full green gate

**Files:**
- Modify: `CLAUDE.md`, `docs/architecture.md`, `docs/project-history.md`
- Create: `docs/adr/0001-lean-single-uv-workspace.md`

**Interfaces:**
- Produces: docs that match reality (greenfield → A1 built); ADR-0001 recording the lean-workspace decision. No code change; the deliverable is honest docs + a green coverage/lint gate across the whole suite.

- [ ] **Step 1: Run the full suite + lint to confirm A1 is green**

Run: `make coverage && make lint`
Expected: all tests pass; coverage ≥ 80%; ruff + mypy clean. Fix any gaps before editing docs.

- [ ] **Step 2: Write ADR-0001**

`docs/adr/0001-lean-single-uv-workspace.md`:
```markdown
# ADR-0001: Lean single-uv-workspace structure (no hextech tooling)

**Status:** Accepted (2026-06-29)

## Context
hexrepo is the structural reference, but it carries heavy tooling (the hextech
scaffolding CLI, per-lib CodeArtifact publishing, Terraform per project/env). NAAF is a
single product: one backend server + one UI + a small set of shared libs.

## Decision
Adopt hexrepo's hexagonal **patterns and code** (Repository/UnitOfWork, CrudRouter,
the {success,data,error} envelope, owner-scoping) inside a single `uv` workspace with
`projects/server`, `projects/ui` (A2), and `libs/<pkg>`. Do **not** port hextech, CodeArtifact,
or Terraform. Only genuinely app-agnostic code (e.g. `crud_router`) becomes a workspace lib.

## Consequences
- Shortest path to a running app; less ceremony.
- If NAAF later needs to host many services or cloud publishing, revisit and consider the
  hextech machinery then (YAGNI until then).
```

- [ ] **Step 3: Reconcile CLAUDE.md**

In `CLAUDE.md`:
- Replace the "A5 status … merged" paragraph and the ADR-0002 orchestration block (which describe unbuilt work) with: a short "Status" line pointing to `docs/project-history.md`, and keep the roadmap as *future* phases.
- Fix the `## Architecture` structure block to the lean layout (`projects/server/src/{domain,adapters,interactors}`, `libs/crud_router`, `projects/ui` reserved for A2).
- In `## Dev commands`, replace the stale Temporal/worker/litellm/deploy lines with the real A1 commands:
```bash
uv sync
docker compose up -d postgres
make db-upgrade            # alembic upgrade head
uv run python -m interactors.cli.seed
make test                  # uv run pytest
make coverage              # 80% gate
make run                   # uvicorn interactors.api.app:create_app --factory --reload
```

- [ ] **Step 4: Reconcile docs/architecture.md and docs/project-history.md**

- `docs/architecture.md`: change framing from "is implemented" to "target patterns". Keep the
  persistence/API sections (they are now the A1 implementation — update any path that differs
  from what was built). Mark the "Agent execution & orchestration" and "Storage port" sections
  as **"Designed; not built — A3+/A4+"**.
- `docs/project-history.md`: rewrite the body to:
```markdown
## Status (2026-06-29)

**A1 control plane — built.** Backend spine: Project + unified WorkItem (epic/feature/task)
with domain-enforced hierarchy and a status transition machine; owner-scoped
Repository/UnitOfWork (ported from hexrepo); envelope-aware CrudRouter; nested-create,
transition, and board APIs; config-only Team + AgentDefinition with a seed; Postgres + Alembic,
SQLite in tests; dev auth. See [plans/2026-06-29-a1-control-plane](superpowers/plans/2026-06-29-a1-control-plane.md).

**Not yet built (designed only):** A2 board UI · A3 Temporal pipeline + runs · A4 sandbox /
egress / GitHub App · A5 Claude Code runtime + LiteLLM · B/C management plane. The
agent/Temporal/sandbox/secrets content in the master design and architecture doc is the
*target*, not current code.
```
- Remove or correct dangling references to `ADR-0002`, `docs/plans/` (now `docs/superpowers/plans/`),
  and `docs/deployment.md` workflows that don't exist.

- [ ] **Step 5: Re-run the gate and commit**

Run: `make coverage && make lint`
Expected: green.

```bash
git add CLAUDE.md docs/architecture.md docs/project-history.md docs/adr/0001-lean-single-uv-workspace.md
git commit -m "docs: reconcile status to A1-built reality; add ADR-0001"
```

- [ ] **Step 6: Push and open the PR**

```bash
git push -u origin feat/a1-control-plane
gh pr create --title "feat: A1 control plane (backend spine)" \
  --body "Implements docs/superpowers/specs/2026-06-29-a1-control-plane-design.md. Domain (Project + unified WorkItem, transitions, hierarchy), owner-scoped Repository/UoW, envelope CrudRouter, nested/transition/board routes, config-only Team, Alembic, seed, reconciled docs. Test plan: make coverage (80% gate) + make lint green."
```

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-06-29-a1-control-plane-design.md`):
- §3 repo structure → Task 1. §4 domain (Project, WorkItem, status machine, hierarchy, errors, board) → Tasks 2–8. §5 persistence (ports, ORM, generic repo, per-entity repos, UoW, owner-scoping, engine, Alembic) → Tasks 10–14. §6 API (CrudRouter, hand-written nested/transition/board, envelope, exception mapping, dev-auth) → Tasks 9, 15–18. §2 Team+AgentDefinition config-only + seed → Tasks 8, 18, 19. §7 testing (unit + SQLite integration, 80% gate) → every task + Task 20. §8 docs reconciliation + ADR-0001 → Task 20. §9 build order mirrors Tasks 1–20. No gaps.

**2. Placeholder scan:** No "TBD"/"implement later". The one place autogenerate output isn't inlined (Alembic `0001_initial.py`, Task 14) is generated by an exact command with a review checklist — acceptable because hand-writing a migration is more error-prone than autogenerate. Every code step shows complete code.

**3. Type consistency:** `validate_transition(current, target)`, `validate_hierarchy(child_kind, parent)`, `build_board_tree(items) -> list[BoardNode]`, `SqlRepository.orm_model/dto`, `SqlUnitOfWork(session_factory, required_filters)` with properties `projects/work_items/teams/agent_definitions`, `CrudRouter(db_dependency, repository, response_dto, create_schema, update_schema, methods, prefix, tags)`, `Envelope{success,data,error,meta}`, `ok(data, meta=None)` — all used identically across tasks. Repository `read/update/delete` take a `str` id; `CrudRouter` passes `id.hex` from the path `UUID`, and hand-written work-item routes use `str` path params directly (consistent — both yield 32-char hex). Schemas omit `owner_id` (stamped by repo) and `UpdateWorkItem` omits `status` (transition-only) — enforced consistently.
