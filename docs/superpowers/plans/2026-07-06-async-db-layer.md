# Async Database Layer (`libs/db`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract NAAF's generic DB machinery into a reusable `libs/db` workspace package that provides both sync and async SQLAlchemy implementations, then back the SSE stream endpoints with an async UnitOfWork so their DB reads no longer block the event loop (the API-freeze root cause).

**Architecture:** A new domain-agnostic `naaf_db` lib holds the sync `SqlRepository`/`SqlUnitOfWorkBase` (moved verbatim) plus new async twins (`AsyncSqlRepository`/`AsyncUnitOfWorkBase`) built on `create_async_engine`. The app keeps its ORM + concrete repositories, binding the lib bases to `domain.errors`. Only the two SSE streams switch to the async UoW; every sync endpoint and the worker are unchanged.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (sync + asyncio), psycopg3 (sync *and* async on the same `postgresql+psycopg://` URL), FastAPI, sse-starlette, pytest + pytest-asyncio, aiosqlite (tests), uv workspace.

## Global Constraints

- Python `>=3.12`; package manager `uv`.
- Async engine reuses the existing `postgresql+psycopg://` URL — **no `asyncpg`**.
- `domain/` must not import from `libs/db` or any adapter (hexagonal purity). The lib defines its own `RecordNotFound`/`IntegrityConflict`; the app binds them to `domain.errors.*` via class attributes.
- Every response stays in the `{success, data, error}` envelope; owner-scoping via `required_filters` is preserved in both sync and async repos.
- Immutability: Pydantic DTOs updated via `model_copy(update=...)`, never mutated.
- Commit format `<type>: <description>`. `make coverage` ≥ 80% and `make lint` (ruff + mypy over `projects/server/src libs/crud_router/src` — extend to `libs/db/src`) must stay green.
- All work on branch `feat/async-db-layer` in `.worktrees/async-db-layer`.

---

### Task 1: Scaffold the `libs/db` package and wire the workspace + dependencies

**Files:**
- Create: `libs/db/pyproject.toml`
- Create: `libs/db/src/naaf_db/__init__.py`
- Create: `libs/db/tests/test_import.py`
- Modify: `pyproject.toml` (root — `[tool.uv.workspace].members`, `[tool.uv.sources]`)
- Modify: `projects/server/pyproject.toml` (`dependencies`, `[tool.uv.sources]`)
- Modify: `Makefile:36` (mypy target — add `libs/db/src`)

**Interfaces:**
- Produces: an importable `naaf_db` package (empty for now) available to `projects/server` as the `naaf-db` workspace dependency.

- [ ] **Step 1: Create the lib package files**

`libs/db/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "naaf-db"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "sqlalchemy[asyncio]>=2.0",
    "pydantic>=2.7",
    "greenlet>=3.0",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "aiosqlite>=0.20"]

[tool.hatch.build.targets.wheel]
packages = ["src/naaf_db"]
```

`libs/db/src/naaf_db/__init__.py`:
```python
"""Generic, domain-agnostic SQLAlchemy machinery: sync + async engines,
repositories, and unit-of-work bases. Apps subclass these with their own ORM
models and concrete repositories."""
```

`libs/db/tests/test_import.py`:
```python
def test_naaf_db_imports():
    import naaf_db  # noqa: F401
```

- [ ] **Step 2: Wire the workspace**

In root `pyproject.toml`, add `"libs/db"` to `[tool.uv.workspace].members` and add under `[tool.uv.sources]`:
```toml
naaf-db = { workspace = true }
```

In `projects/server/pyproject.toml`, add `"naaf-db"` to `dependencies` and under `[tool.uv.sources]`:
```toml
naaf-db = { workspace = true }
```

Also add the runtime + test deps the async layer needs to `projects/server/pyproject.toml` `dependencies` (SQLAlchemy async extra pulls greenlet) and its dev group:
```toml
# dependencies: change "sqlalchemy>=2.0" to:
"sqlalchemy[asyncio]>=2.0",
```
Add `aiosqlite>=0.20` and `pytest-asyncio>=0.24` to the server's existing test/dev dependency group (match the file's current dev-deps style).

In `Makefile`, extend the mypy line (currently `uv run mypy projects/server/src libs/crud_router/src`) to include `libs/db/src`.

- [ ] **Step 3: Sync and verify the import test fails-then-passes**

Run: `uv sync`
Run: `uv run --package naaf-db pytest libs/db/tests/test_import.py -v`
Expected: PASS. (If `naaf_db` were missing it would ERROR on import.)

- [ ] **Step 4: Enable async tests**

Create `libs/db/pytest.ini` (or add to the lib's `pyproject.toml`) so pytest-asyncio auto-detects async tests:
```ini
[pytest]
asyncio_mode = auto
```
Confirm the server test config also has `asyncio_mode = auto` (add to `projects/server/pyproject.toml` `[tool.pytest.ini_options]`, or its `pytest.ini`, matching the existing config location).

- [ ] **Step 5: Commit**

```bash
git add libs/db pyproject.toml projects/server/pyproject.toml Makefile uv.lock
git commit -m "chore: scaffold libs/db workspace package + async deps"
```

---

### Task 2: Move the generic **sync** machinery into `libs/db`

Move `ports`, errors, `engine`, `SqlRepository`, and a new `SqlUnitOfWorkBase` into the lib **verbatim in behavior**, dropping their app/domain imports. The app re-binds them so all existing sync code and tests keep passing unchanged.

**Files:**
- Create: `libs/db/src/naaf_db/errors.py`
- Create: `libs/db/src/naaf_db/ports.py`
- Create: `libs/db/src/naaf_db/engine.py`
- Create: `libs/db/src/naaf_db/repository.py`
- Create: `libs/db/src/naaf_db/uow.py`
- Create: `libs/db/tests/test_sync_repository.py`
- Modify: `projects/server/src/adapters/database/repository.py` (becomes a thin bind)
- Modify: `projects/server/src/adapters/database/engine.py` (re-export from lib)
- Modify: `projects/server/src/adapters/database/ports.py` (re-export from lib)
- Modify: `projects/server/src/adapters/database/uow.py` (subclass lib base)

**Interfaces:**
- Produces:
  - `naaf_db.errors.RecordNotFound`, `naaf_db.errors.IntegrityConflict`
  - `naaf_db.ports.PaginatedResult[DTO]`, `naaf_db.ports.Repository`
  - `naaf_db.engine.build_engine(url, **kw) -> Engine`, `build_session_factory(engine) -> sessionmaker`
  - `naaf_db.repository.SqlRepository[DTO]` with overridable class attrs `not_found_error`, `conflict_error`, and `orm_model`/`dto`.
  - `naaf_db.uow.SqlUnitOfWorkBase` with `.session`, `transaction()`, `_repo(name, cls)`.
- Consumes (in app): `domain.errors.RecordNotFound`, `domain.errors.IntegrityConflict`, `adapters.database.orm.Base`.

- [ ] **Step 1: Write the failing lib repository test**

`libs/db/tests/test_sync_repository.py`:
```python
import pytest
from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from naaf_db.engine import build_engine
from naaf_db.errors import RecordNotFound
from naaf_db.repository import SqlRepository


class Base(DeclarativeBase):
    pass


class WidgetRow(Base):
    __tablename__ = "widgets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)


class Widget(BaseModel):
    id: str
    owner_id: str
    name: str


class WidgetRepo(SqlRepository[Widget]):
    orm_model = WidgetRow
    dto = Widget


@pytest.fixture
def session():
    engine = build_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_create_read_roundtrip_with_owner_scope(session):
    repo = WidgetRepo(session, required_filters={"owner_id": "u1"})
    created = repo.create(Widget(id="w1", owner_id="", name="a"))
    session.flush()
    assert created.owner_id == "u1"
    assert repo.read("w1").name == "a"


def test_read_missing_raises_record_not_found(session):
    repo = WidgetRepo(session, required_filters={"owner_id": "u1"})
    with pytest.raises(RecordNotFound):
        repo.read("nope")


def test_owner_scope_hides_other_owners_rows(session):
    WidgetRepo(session, required_filters={"owner_id": "u1"}).create(Widget(id="w1", owner_id="", name="a"))
    session.flush()
    with pytest.raises(RecordNotFound):
        WidgetRepo(session, required_filters={"owner_id": "u2"}).read("w1")
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run --package naaf-db pytest libs/db/tests/test_sync_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'naaf_db.repository'`.

- [ ] **Step 3: Create the lib errors + ports**

`libs/db/src/naaf_db/errors.py`:
```python
class RecordNotFound(Exception):
    """Raised when a row is not found (or is out of the caller's owner scope)."""


class IntegrityConflict(Exception):
    """Raised on a DB integrity violation (unique/FK)."""
```

`libs/db/src/naaf_db/ports.py` — copy `PaginatedResult` and the `Repository` protocol from `projects/server/src/adapters/database/ports.py` verbatim (the `UnitOfWork` protocol with named naaf properties stays in the app):
```python
from __future__ import annotations

from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

DTO = TypeVar("DTO")


class PaginatedResult(BaseModel, Generic[DTO]):  # noqa: UP046
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
```

- [ ] **Step 4: Create the lib engine**

`libs/db/src/naaf_db/engine.py` — move `build_engine`/`build_session_factory` from `adapters/database/engine.py` verbatim (the `_json_default` serializer included):
```python
import json
from datetime import date, datetime

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker


def _json_default(obj: object) -> str:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def build_engine(db_url: str, **kwargs: object) -> Engine:
    return create_engine(
        db_url,
        future=True,
        json_serializer=lambda o: json.dumps(o, default=_json_default),
        **kwargs,
    )


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
```

- [ ] **Step 5: Create the lib `SqlRepository`**

`libs/db/src/naaf_db/repository.py` — move the class from `adapters/database/repository.py` verbatim, with two changes: (a) drop `from adapters.database.orm import Base` — type `orm_model` as `type[Any]`; (b) replace the `domain.errors` import with overridable class attributes bound to the lib errors:
```python
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel
from sqlalchemy import Delete, Select, asc, desc, func, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError as SqlIntegrityError
from sqlalchemy.orm import Session

from naaf_db.errors import IntegrityConflict, RecordNotFound
from naaf_db.ports import PaginatedResult

DTO = TypeVar("DTO", bound=BaseModel)


class SqlRepository(Generic[DTO]):  # noqa: UP046
    """Generic DTO-in/DTO-out repository. Subclass and set orm_model + dto.

    Subclasses may override not_found_error / conflict_error to raise
    application-specific exceptions (e.g. the app binds them to domain.errors).
    """

    orm_model: type[Any]
    dto: type[BaseModel]
    not_found_error: type[Exception] = RecordNotFound
    conflict_error: type[Exception] = IntegrityConflict

    def __init__(self, session: Session, required_filters: dict[str, Any] | None = None):
        self.session = session
        self.required_filters = required_filters or {}

    # ... (copy _to_dto, _base_select, _apply_filters, _order verbatim) ...
```
Then in `_get_one_row`, `create`, `update` replace `RecordNotFound(...)` → `self.not_found_error(...)` and `IntegrityConflict(...)` → `self.conflict_error(...)`. Copy `read`, `read_multi`, `delete`, `delete_where` verbatim. (The full body is the current `adapters/database/repository.py` with those three symbol substitutions.)

- [ ] **Step 6: Create the lib `SqlUnitOfWorkBase`**

`libs/db/src/naaf_db/uow.py` — extract the session + `transaction()` + `_repo` mechanics from `adapters/database/uow.py`:
```python
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session, sessionmaker


class SqlUnitOfWorkBase:
    """Owns one session + transaction boundary. Subclasses add named repository
    properties via `_repo`. Repositories share the session and apply
    required_filters for owner-scoping."""

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
    def transaction(self) -> Iterator["SqlUnitOfWorkBase"]:
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
```

- [ ] **Step 7: Run the lib test — it should pass**

Run: `uv run --package naaf-db pytest libs/db/tests/test_sync_repository.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Re-bind the app to the lib (keep behavior identical)**

`adapters/database/ports.py` — replace body with a re-export so existing imports keep working:
```python
from naaf_db.ports import PaginatedResult, Repository  # noqa: F401

# The app-specific UnitOfWork protocol (named naaf repositories) stays here:
from __future__ import annotations  # (keep at top per lint)
# ... retain the existing `class UnitOfWork(Protocol)` block unchanged,
#     importing Repository/PaginatedResult from naaf_db.ports above.
```

`adapters/database/engine.py` — replace body with:
```python
from naaf_db.engine import build_engine, build_session_factory  # noqa: F401
```

`adapters/database/repository.py` — replace body with a thin bind to domain errors:
```python
from domain.errors import IntegrityConflict, RecordNotFound
from naaf_db.repository import SqlRepository as _SqlRepository


class SqlRepository(_SqlRepository):
    not_found_error = RecordNotFound
    conflict_error = IntegrityConflict
```
(All concrete repos in `repositories.py` import `SqlRepository` from `adapters.database.repository`, so they now get the domain-error binding automatically — no change to `repositories.py`.)

`adapters/database/uow.py` — change `class SqlUnitOfWork:` to subclass the lib base and delete the duplicated `__init__`/`session`/`transaction`/`_repo` (keep all the `@property` repos and `delete_project_cascade`):
```python
from naaf_db.uow import SqlUnitOfWorkBase
# ...
class SqlUnitOfWork(SqlUnitOfWorkBase):
    # remove __init__, session, transaction, _repo (now inherited)
    @property
    def attachments(self) -> AttachmentRepository:
        return self._repo("attachments", AttachmentRepository)
    # ... all other repo properties + delete_project_cascade unchanged ...
```

- [ ] **Step 9: Run the FULL server suite — nothing should regress**

Run: `cd projects/server && uv run pytest -q`
Expected: all existing tests PASS (the move is behavior-preserving).

- [ ] **Step 10: Lint**

Run: `make lint`
Expected: ruff + mypy green (mypy now also covers `libs/db/src`).

- [ ] **Step 11: Commit**

```bash
git add libs/db projects/server/src/adapters/database
git commit -m "refactor: move generic sync DB machinery into libs/db (naaf_db)"
```

---

### Task 3: Add the async engine + session manager to `libs/db`

**Files:**
- Modify: `libs/db/src/naaf_db/engine.py` (add async builders)
- Create: `libs/db/tests/test_async_engine.py`

**Interfaces:**
- Produces:
  - `naaf_db.engine.build_async_engine(db_url, **kw) -> AsyncEngine` — accepts the sync `postgresql+psycopg://` URL and uses it directly (psycopg3 async); also accepts `sqlite+aiosqlite://`.
  - `naaf_db.engine.build_async_session_factory(engine) -> async_sessionmaker[AsyncSession]`.

- [ ] **Step 1: Write the failing async engine test**

`libs/db/tests/test_async_engine.py`:
```python
import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from naaf_db.engine import build_async_engine, build_async_session_factory


@pytest.mark.asyncio
async def test_async_session_executes_a_query():
    engine = build_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    factory = build_async_session_factory(engine)
    async with factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    await engine.dispose()
```

- [ ] **Step 2: Run it — fails**

Run: `uv run --package naaf-db pytest libs/db/tests/test_async_engine.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_async_engine'`.

- [ ] **Step 3: Add the async builders**

Append to `libs/db/src/naaf_db/engine.py`:
```python
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_async_engine(db_url: str, **kwargs: object) -> AsyncEngine:
    """Async engine for the SAME URL scheme used sync — psycopg3 is async-capable,
    so `postgresql+psycopg://...` works unchanged; tests pass `sqlite+aiosqlite://`."""
    return create_async_engine(
        db_url,
        future=True,
        json_serializer=lambda o: json.dumps(o, default=_json_default),
        **kwargs,
    )


def build_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False)
```

- [ ] **Step 4: Run it — passes**

Run: `uv run --package naaf-db pytest libs/db/tests/test_async_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add libs/db
git commit -m "feat: add async engine + session factory to naaf_db"
```

---

### Task 4: Add the generic `AsyncSqlRepository` + `AsyncUnitOfWorkBase`

Full CRUD parity with the sync base, using `AsyncSession` and `await`.

**Files:**
- Create: `libs/db/src/naaf_db/async_repository.py`
- Create: `libs/db/src/naaf_db/async_uow.py`
- Create: `libs/db/tests/test_async_repository.py`

**Interfaces:**
- Consumes: `naaf_db.ports.PaginatedResult`, `naaf_db.errors.*`.
- Produces:
  - `naaf_db.async_repository.AsyncSqlRepository[DTO]` — `async create/read/read_multi/update/delete/delete_where`, same `orm_model`/`dto`/`not_found_error`/`conflict_error`/`required_filters` contract and the same `__in/__like/__gte/__lte/__gt/__lt/__ne/__isnull` filter suffixes as the sync base.
  - `naaf_db.async_uow.AsyncUnitOfWorkBase` — `.session` (`AsyncSession`), `async transaction()` (`@asynccontextmanager`), `_repo(name, cls)`.

- [ ] **Step 1: Write the failing async repository test**

`libs/db/tests/test_async_repository.py`:
```python
import pytest
from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from naaf_db.async_repository import AsyncSqlRepository
from naaf_db.engine import build_async_engine
from naaf_db.errors import RecordNotFound


class Base(DeclarativeBase):
    pass


class WidgetRow(Base):
    __tablename__ = "widgets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)


class Widget(BaseModel):
    id: str
    owner_id: str
    name: str


class AsyncWidgetRepo(AsyncSqlRepository[Widget]):
    orm_model = WidgetRow
    dto = Widget


@pytest.fixture
async def factory():
    engine = build_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_async_create_read_and_owner_scope(factory):
    async with factory() as session:
        repo = AsyncWidgetRepo(session, required_filters={"owner_id": "u1"})
        await repo.create(Widget(id="w1", owner_id="", name="a"))
        await session.flush()
        got = await repo.read("w1")
        assert got.owner_id == "u1" and got.name == "a"


@pytest.mark.asyncio
async def test_async_read_missing_raises(factory):
    async with factory() as session:
        repo = AsyncWidgetRepo(session, required_filters={"owner_id": "u1"})
        with pytest.raises(RecordNotFound):
            await repo.read("nope")


@pytest.mark.asyncio
async def test_async_read_multi_filters_and_orders(factory):
    async with factory() as session:
        repo = AsyncWidgetRepo(session, required_filters={"owner_id": "u1"})
        for i in (2, 1, 3):
            await repo.create(Widget(id=f"w{i}", owner_id="", name=str(i)))
        await session.flush()
        page = await repo.read_multi(filters={"name__gte": "2"}, order_by="name")
        assert [w.name for w in page.results] == ["2", "3"]
        assert page.total == 2
```

- [ ] **Step 2: Run it — fails**

Run: `uv run --package naaf-db pytest libs/db/tests/test_async_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'naaf_db.async_repository'`.

- [ ] **Step 3: Implement `AsyncSqlRepository`**

`libs/db/src/naaf_db/async_repository.py` — mirror the sync base. The query-building helpers (`_base_select`, `_apply_filters`, `_order`) are **identical** (they build `Select` objects, no I/O); only the execute/flush/refresh calls are awaited:
```python
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel
from sqlalchemy import Delete, Select, asc, desc, func, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError as SqlIntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from naaf_db.errors import IntegrityConflict, RecordNotFound
from naaf_db.ports import PaginatedResult

DTO = TypeVar("DTO", bound=BaseModel)


class AsyncSqlRepository(Generic[DTO]):  # noqa: UP046
    orm_model: type[Any]
    dto: type[BaseModel]
    not_found_error: type[Exception] = RecordNotFound
    conflict_error: type[Exception] = IntegrityConflict

    def __init__(self, session: AsyncSession, required_filters: dict[str, Any] | None = None):
        self.session = session
        self.required_filters = required_filters or {}

    def _to_dto(self, row: Any) -> DTO:
        data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        return self.dto(**data)  # type: ignore[return-value]

    def _base_select(self) -> Select:
        query = select(self.orm_model)
        for key, value in self.required_filters.items():
            query = query.where(getattr(self.orm_model, key) == value)
        return query

    def _apply_filters(self, query: Select, filters: dict[str, Any]) -> Select:
        # IDENTICAL to naaf_db.repository.SqlRepository._apply_filters
        # (copy the __in/__like/__isnull/__gte/__lte/__gt/__lt/__ne/else block verbatim)
        ...

    def _order(self, query: Select, order_by: str | None) -> Select:
        if not order_by:
            return query
        direction = desc if order_by.startswith("-") else asc
        return query.order_by(direction(order_by.lstrip("-")))

    async def _get_one_row(self, id: str) -> Any:
        query = self._base_select().where(self.orm_model.id == id)
        row = (await self.session.execute(query)).scalar_one_or_none()
        if row is None:
            raise self.not_found_error(f"{self.orm_model.__name__} {id} not found")
        return row

    async def create(self, dto: BaseModel) -> DTO:
        data = {k: v for k, v in dto.model_dump().items() if v is not None}
        data.update(self.required_filters)
        row = self.orm_model(**data)
        self.session.add(row)
        try:
            await self.session.flush()
        except SqlIntegrityError as err:
            await self.session.rollback()
            raise self.conflict_error(str(err.orig)) from err
        await self.session.refresh(row)
        return self._to_dto(row)

    async def read(self, id: str) -> DTO:
        return self._to_dto(await self._get_one_row(id))

    async def read_multi(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str = "-created_at",
    ) -> PaginatedResult[DTO]:
        filters = filters or {}
        query = self._order(self._apply_filters(self._base_select(), filters), order_by)
        count_query = self._apply_filters(
            select(func.count()).select_from(self.orm_model), filters
        )
        for key, value in self.required_filters.items():
            count_query = count_query.where(getattr(self.orm_model, key) == value)
        total = int((await self.session.execute(count_query)).scalar_one())
        if page_size > 0 and page_number >= 1:
            query = query.offset((page_number - 1) * page_size).limit(page_size)
        rows = (await self.session.execute(query)).scalars().all()
        return PaginatedResult[self.dto](  # type: ignore[name-defined]
            results=[self._to_dto(r) for r in rows],
            total=total,
            page_size=page_size,
            page_number=page_number,
        )

    async def update(self, id: str, dto: BaseModel) -> DTO:
        row = await self._get_one_row(id)
        for key, value in dto.model_dump(exclude_unset=True).items():
            if key in ("id", "owner_id", "created_at"):
                continue
            setattr(row, key, value)
        try:
            await self.session.flush()
        except SqlIntegrityError as err:
            await self.session.rollback()
            raise self.conflict_error(str(err.orig)) from err
        await self.session.refresh(row)
        return self._to_dto(row)

    async def delete(self, id: str) -> None:
        row = await self._get_one_row(id)
        await self.session.delete(row)
        await self.session.flush()

    async def delete_where(self, **filters: Any) -> int:
        stmt: Delete = sql_delete(self.orm_model)
        for key, value in filters.items():
            if key.endswith("__in"):
                stmt = stmt.where(getattr(self.orm_model, key[:-4]).in_(value))
            else:
                stmt = stmt.where(getattr(self.orm_model, key) == value)
        for key, value in self.required_filters.items():
            stmt = stmt.where(getattr(self.orm_model, key) == value)
        result = cast(CursorResult, await self.session.execute(stmt))
        await self.session.flush()
        return int(result.rowcount or 0)
```
(Copy the `_apply_filters` body verbatim from `naaf_db/repository.py`.)

- [ ] **Step 4: Implement `AsyncUnitOfWorkBase`**

`libs/db/src/naaf_db/async_uow.py`:
```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class AsyncUnitOfWorkBase:
    """Async sibling of SqlUnitOfWorkBase. Owns one AsyncSession + transaction."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        required_filters: dict[str, Any] | None = None,
    ):
        self._session_factory = session_factory
        self._required_filters = required_filters or {}
        self._session: AsyncSession | None = None
        self._repos: dict[str, Any] = {}

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["AsyncUnitOfWorkBase"]:
        session = self.session
        try:
            yield self
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            self._session = None
            self._repos = {}

    def _repo(self, name: str, cls: type) -> Any:
        if name not in self._repos:
            self._repos[name] = cls(self.session, required_filters=self._required_filters)
        return self._repos[name]
```

- [ ] **Step 5: Run the async repo tests — pass**

Run: `uv run --package naaf-db pytest libs/db/tests/test_async_repository.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Lint + commit**

Run: `make lint`
```bash
git add libs/db
git commit -m "feat: add generic AsyncSqlRepository + AsyncUnitOfWorkBase to naaf_db"
```

---

### Task 5: App async concrete repos + `AsyncUnitOfWork`

**Files:**
- Modify: `projects/server/src/adapters/database/repository.py` (add async bind)
- Modify: `projects/server/src/adapters/database/repositories.py` (add 2 async repos)
- Modify: `projects/server/src/adapters/database/uow.py` (add `AsyncUnitOfWork`)
- Create: `projects/server/tests/adapters/database/test_async_uow.py`

**Interfaces:**
- Consumes: `naaf_db.async_repository.AsyncSqlRepository`, `naaf_db.async_uow.AsyncUnitOfWorkBase`, `domain.errors.*`, `adapters.database.orm.{AgentEventRow, RunEventRow}`, `domain` DTOs `AgentEvent`, `RunEvent`.
- Produces:
  - `adapters.database.repository.AsyncSqlRepository` (domain-error-bound base).
  - `AsyncAgentEventRepository.list_after(scope, after, limit=200) -> list[AgentEvent]`.
  - `AsyncRunEventRepository` (base `read_multi` only).
  - `adapters.database.uow.AsyncUnitOfWork` with `.agent_events` and `.run_events`.

- [ ] **Step 1: Write the failing async UoW test**

`projects/server/tests/adapters/database/test_async_uow.py`:
```python
import pytest
from adapters.database.orm import Base
from adapters.database.uow import AsyncUnitOfWork
from domain.agent.events import AgentEvent, stream_scope
from naaf_db.engine import build_async_engine, build_async_session_factory
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def async_factory():
    engine = build_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield build_async_session_factory(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_async_agent_events_list_after(async_factory):
    scope = stream_scope(thread_id="t1")
    uow = AsyncUnitOfWork(async_factory, required_filters={"owner_id": "u1"})
    async with uow.transaction():
        await uow.agent_events.create(AgentEvent(owner_id="", scope=scope, kind="status", payload={}))
        await uow.agent_events.create(AgentEvent(owner_id="", scope=scope, kind="final", payload={}))
    async with uow.transaction():
        events = await uow.agent_events.list_after(scope, after=0, limit=10)
    assert [e.kind for e in events] == ["status", "final"]
    assert events[0].seq < events[1].seq
```
(Confirm the exact `AgentEvent` import path / constructor from `domain/agent/events.py`; adjust the import if the DTO lives elsewhere.)

- [ ] **Step 2: Run it — fails**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_async_uow.py -v`
Expected: FAIL — `ImportError: cannot import name 'AsyncUnitOfWork'`.

- [ ] **Step 3: Add the app async base bind**

Append to `adapters/database/repository.py`:
```python
from naaf_db.async_repository import AsyncSqlRepository as _AsyncSqlRepository


class AsyncSqlRepository(_AsyncSqlRepository):
    not_found_error = RecordNotFound
    conflict_error = IntegrityConflict
```

- [ ] **Step 4: Add the async concrete repos**

In `adapters/database/repositories.py`, add (import `AsyncSqlRepository` from `adapters.database.repository`):
```python
class AsyncAgentEventRepository(AsyncSqlRepository[AgentEvent]):
    orm_model = AgentEventRow
    dto = AgentEvent

    async def list_after(self, scope: str, after: int, limit: int = 200) -> list[AgentEvent]:
        page = await self.read_multi(
            filters={"scope": scope, "seq__gt": after},
            order_by="seq",
            page_size=limit,
        )
        return page.results


class AsyncRunEventRepository(AsyncSqlRepository[RunEvent]):
    orm_model = RunEventRow
    dto = RunEvent
```
(These are read-only for the streams; the sync repos remain the write path, so no async `create` override is needed.)

- [ ] **Step 5: Add `AsyncUnitOfWork`**

In `adapters/database/uow.py`:
```python
from naaf_db.async_uow import AsyncUnitOfWorkBase
from adapters.database.repositories import AsyncAgentEventRepository, AsyncRunEventRepository


class AsyncUnitOfWork(AsyncUnitOfWorkBase):
    @property
    def agent_events(self) -> AsyncAgentEventRepository:
        return self._repo("agent_events", AsyncAgentEventRepository)

    @property
    def run_events(self) -> AsyncRunEventRepository:
        return self._repo("run_events", AsyncRunEventRepository)
```

- [ ] **Step 6: Run the async UoW test — pass**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_async_uow.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add projects/server/src/adapters/database projects/server/tests/adapters/database/test_async_uow.py
git commit -m "feat: async AgentEvent/RunEvent repos + AsyncUnitOfWork"
```

---

### Task 6: Wire the async engine into the app (state, lifespan, dependency)

**Files:**
- Modify: `projects/server/src/interactors/api/app.py`
- Modify: `projects/server/src/interactors/api/deps.py`
- Modify: `projects/server/tests/conftest.py` (async factory for the app in tests)
- Create: `projects/server/tests/api/test_async_dep.py`

**Interfaces:**
- Consumes: `naaf_db.engine.build_async_engine`, `build_async_session_factory`, `adapters.database.uow.AsyncUnitOfWork`.
- Produces:
  - `app.state.async_session_factory` (an `async_sessionmaker`).
  - `deps.get_async_uow(request, owner_id) -> AsyncIterator[AsyncUnitOfWork]`.
  - `create_app(..., async_session_factory=None)` optional override (mirrors `session_factory`) so tests can inject an aiosqlite factory.

- [ ] **Step 1: Write the failing test for the async dependency**

Add a temporary probe route in the test (or assert via an existing async stream once Task 7 lands). Minimal direct test — `projects/server/tests/api/test_async_dep.py`:
```python
import pytest
from adapters.database.uow import AsyncUnitOfWork
from interactors.api.deps import get_async_uow


def test_get_async_uow_is_async_generator():
    # get_async_uow must be an async generator function yielding an AsyncUnitOfWork
    import inspect
    assert inspect.isasyncgenfunction(get_async_uow)
```
(Behavioral coverage of `get_async_uow` comes through the SSE tests in Task 7; this guards the signature.)

- [ ] **Step 2: Run it — fails**

Run: `cd projects/server && uv run pytest tests/api/test_async_dep.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_async_uow'`.

- [ ] **Step 3: Build the async engine at app startup + dispose on shutdown**

In `interactors/api/app.py`, extend `create_app`:
```python
from contextlib import asynccontextmanager

from naaf_db.engine import build_async_engine, build_async_session_factory


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
    async_session_factory=None,
) -> FastAPI:
    settings = settings or Settings()
    if session_factory is None:
        engine = build_engine(settings.db_url)
        session_factory = build_session_factory(engine)

    async_engine = None
    if async_session_factory is None:
        async_engine = build_async_engine(settings.db_url)
        async_session_factory = build_async_session_factory(async_engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if async_engine is not None:
            await async_engine.dispose()

    app = FastAPI(title="NAAF Control Plane", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.async_session_factory = async_session_factory
    app.state.storage = build_storage(settings)
    # ... rest unchanged ...
```
Note: `settings.db_url` is `postgresql+psycopg://...` in prod — `build_async_engine` uses it directly (psycopg3 async).

- [ ] **Step 4: Add the async dependency**

In `interactors/api/deps.py`:
```python
from collections.abc import AsyncIterator

from adapters.database.uow import AsyncUnitOfWork


async def get_async_uow(
    request: Request, owner_id: str = Depends(get_owner_id)
) -> AsyncIterator[AsyncUnitOfWork]:
    uow = AsyncUnitOfWork(
        request.app.state.async_session_factory,
        required_filters={"owner_id": owner_id},
    )
    async with uow.transaction():
        yield uow
```

- [ ] **Step 5: Give tests an aiosqlite async factory**

In `projects/server/tests/conftest.py`, share ONE aiosqlite engine between the sync tables and the async factory so both see the same in-memory DB. Update the `client` fixture:
```python
import pytest_asyncio  # if needed
from naaf_db.engine import build_async_engine, build_async_session_factory


@pytest.fixture
def async_session_factory():
    engine = build_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    return build_async_session_factory(engine)


@pytest.fixture
def client(session_factory, async_session_factory):
    app = create_app(
        settings=Settings(),
        session_factory=session_factory,
        async_session_factory=async_session_factory,
    )
    return TestClient(app)
```
NOTE: sync `session_factory` and `async_session_factory` are **separate in-memory DBs**. For the SSE tests in Task 7, seed events through the **async** factory (or a shared-file sqlite URL like `sqlite+aiosqlite:///file:memdb1?mode=memory&cache=shared&uri=true` paired with the sync `sqlite:///file:memdb1?...`) so the stream can read what the test wrote. Use the shared-cache URL approach in Task 7's fixture.

- [ ] **Step 6: Run — pass; then full suite**

Run: `cd projects/server && uv run pytest tests/api/test_async_dep.py -v`
Expected: PASS.
Run: `cd projects/server && uv run pytest -q`
Expected: all PASS (TestClient runs lifespan; async engine disposes cleanly).

- [ ] **Step 7: Commit**

```bash
git add projects/server/src/interactors/api/app.py projects/server/src/interactors/api/deps.py projects/server/tests/conftest.py projects/server/tests/api/test_async_dep.py
git commit -m "feat: async engine on app.state + lifespan dispose + get_async_uow"
```

---

### Task 7: Convert the activity SSE streams to the async UoW (+ disconnect exit)

**Files:**
- Modify: `projects/server/src/interactors/api/routes/activity.py` (the `_stream` generator)
- Create: `projects/server/tests/api/test_activity_stream_async.py`
- Create: `projects/server/tests/adapters/database/test_async_pg_smoke.py` (Postgres smoke, opt-in)

**Interfaces:**
- Consumes: `app.state.async_session_factory`, `AsyncUnitOfWork.agent_events.list_after`, `request.is_disconnected()`.
- Produces: async `_stream` that never runs sync DB I/O on the event loop.

- [ ] **Step 1: Write the failing async stream test**

`projects/server/tests/api/test_activity_stream_async.py` — seed two events, assert the stream yields both then closes on `final`. Use a **shared in-memory** sqlite so sync-seed + async-read see the same DB:
```python
import json
import pytest
from adapters.database.orm import Base
from interactors.api.app import create_app
from interactors.api.settings import Settings
from naaf_db.engine import (
    build_async_engine, build_async_session_factory, build_engine, build_session_factory,
)
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

SHARED = "file:memdb_activity?mode=memory&cache=shared&uri=true"


@pytest.fixture
def app_client():
    sync_engine = build_engine(f"sqlite:///{SHARED}", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(sync_engine)
    async_engine = build_async_engine(f"sqlite+aiosqlite:///{SHARED}", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    app = create_app(
        settings=Settings(),
        session_factory=build_session_factory(sync_engine),
        async_session_factory=build_async_session_factory(async_engine),
    )
    return TestClient(app)


def test_activity_stream_yields_events_then_closes(app_client):
    # Seed via the sync UoW (the write path), through the API's session_factory
    from adapters.database.uow import SqlUnitOfWork
    from domain.agent.events import AgentEvent, stream_scope
    scope_thread = "t-async-1"
    sf = app_client.app.state.session_factory
    uow = SqlUnitOfWork(sf, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.agent_events.create(AgentEvent(owner_id="", scope=stream_scope(thread_id=scope_thread), kind="status", payload={}))
        uow.agent_events.create(AgentEvent(owner_id="", scope=stream_scope(thread_id=scope_thread), kind="final", payload={}))

    with app_client.stream("GET", f"/threads/{scope_thread}/activity/stream?after=0") as r:
        body = "".join(chunk for chunk in r.iter_text())
    kinds = [json.loads(line[6:])["kind"] for line in body.splitlines() if line.startswith("data: ")]
    assert kinds == ["status", "final"]
```

- [ ] **Step 2: Run it — fails**

Run: `cd projects/server && uv run pytest tests/api/test_activity_stream_async.py -v`
Expected: FAIL — the stream currently uses the sync `SqlUnitOfWork` and reads a different (empty) DB, so it yields nothing (assertion fails) — or errors on the shared-cache wiring. Confirm RED before proceeding.

- [ ] **Step 3: Convert `_stream` to async UoW + disconnect check**

In `activity.py`, change `_stream` to take the async factory and use `AsyncUnitOfWork`:
```python
from adapters.database.uow import AsyncUnitOfWork


def _stream(request: Request, owner_id: str, scope: str, after: int) -> EventSourceResponse:
    async def gen():
        cursor = after
        deadline = time.monotonic() + _MAX_SECONDS
        factory = request.app.state.async_session_factory
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                return
            uow = AsyncUnitOfWork(factory, required_filters={"owner_id": owner_id})
            async with uow.transaction():
                rows = await uow.agent_events.list_after(scope, cursor, limit=200)
            for ev in rows:
                cursor = ev.seq
                yield {"data": _out(ev).model_dump_json()}
                if ev.kind in (EVENT_FINAL, EVENT_ERROR):
                    return
            await asyncio.sleep(_POLL_SECONDS)

    return EventSourceResponse(gen())
```
(The two stream route functions `thread_activity_stream`/`run_activity_stream` already pass `request`, `owner_id`, `scope`, `after` — no signature change needed. The sync replay endpoints `thread_activity`/`run_activity` keep using the sync `get_uow` — unchanged.)

- [ ] **Step 4: Run the async stream test — pass**

Run: `cd projects/server && uv run pytest tests/api/test_activity_stream_async.py -v`
Expected: PASS (yields `["status", "final"]`).

- [ ] **Step 5: Add the Postgres async smoke test (opt-in)**

`projects/server/tests/adapters/database/test_async_pg_smoke.py`:
```python
import os
import pytest

PG = os.environ.get("NAAF_TEST_PG_URL")  # e.g. postgresql+psycopg://naaf:naaf@localhost:5432/naaf


@pytest.mark.skipif(not PG, reason="set NAAF_TEST_PG_URL to run the Postgres async smoke test")
@pytest.mark.asyncio
async def test_async_uow_reads_agent_events_on_postgres():
    from adapters.database.uow import AsyncUnitOfWork
    from domain.agent.events import stream_scope
    from naaf_db.engine import build_async_engine, build_async_session_factory

    engine = build_async_engine(PG)
    factory = build_async_session_factory(engine)
    uow = AsyncUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    async with uow.transaction():
        # read-only: must not raise and must return a list
        rows = await uow.agent_events.list_after(stream_scope(thread_id="nonexistent"), 0, 10)
    assert rows == []
    await engine.dispose()
```

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/api/routes/activity.py projects/server/tests/api/test_activity_stream_async.py projects/server/tests/adapters/database/test_async_pg_smoke.py
git commit -m "fix: activity SSE streams use async UoW (unblock the event loop)"
```

---

### Task 8: Convert the run-events SSE stream to the async UoW

**Files:**
- Modify: `projects/server/src/interactors/api/routes/runs.py` (`stream_run_events` generator only)
- Create: `projects/server/tests/api/test_run_events_stream_async.py`

**Interfaces:**
- Consumes: `app.state.async_session_factory`, `AsyncUnitOfWork.run_events.read_multi`, `request.is_disconnected()`.

- [ ] **Step 1: Write the failing async run-events stream test**

`projects/server/tests/api/test_run_events_stream_async.py` — mirror Task 7's shared-sqlite fixture (use a distinct shared name `memdb_runev`). Seed a run + two run_events via the sync UoW, then assert the stream yields them and closes on `RUN_FINISHED`. (Follow the exact `RunEvent`/`Run` constructors used in `projects/server/tests` — reuse an existing run-events test's setup helpers.)

- [ ] **Step 2: Run it — fails (RED).**

Run: `cd projects/server && uv run pytest tests/api/test_run_events_stream_async.py -v`
Expected: FAIL (stream reads the empty sync DB, yields nothing).

- [ ] **Step 3: Convert `stream_run_events`'s `gen()` to async UoW**

Keep the upfront sync owner-check (`uow.runs.read(id.hex)` via sync `SqlUnitOfWork`) — it runs once before streaming, off the hot loop. Replace the polling loop:
```python
    async def gen():
        cursor = after
        deadline = time.monotonic() + _SSE_MAX_SECONDS
        factory = request.app.state.async_session_factory
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                return
            auow = AsyncUnitOfWork(factory, required_filters={"owner_id": owner_id})
            async with auow.transaction():
                rows = (await auow.run_events.read_multi(
                    filters={"run_id": id.hex, "seq__gt": cursor},
                    order_by="seq",
                    page_size=0,
                )).results
            for ev in rows:
                cursor = ev.seq
                yield {"data": _run_event_out(ev).model_dump_json()}
                if ev.type == EventType.RUN_FINISHED:
                    return
            await asyncio.sleep(_SSE_POLL_SECONDS)
```
Add `from adapters.database.uow import AsyncUnitOfWork` to the imports.

- [ ] **Step 4: Run it — pass.**

Run: `cd projects/server && uv run pytest tests/api/test_run_events_stream_async.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/routes/runs.py projects/server/tests/api/test_run_events_stream_async.py
git commit -m "fix: run-events SSE stream uses async UoW"
```

---

### Task 9: Full verification, docs, and PR

**Files:**
- Modify: `docs/project-history.md` (note the async DB layer + freeze fix)
- Modify: `CLAUDE.md` (Architecture: add `libs/db` to the tree; note sync vs async UoW)

- [ ] **Step 1: Full suite + coverage**

Run: `make coverage`
Expected: PASS, total coverage ≥ 80%. If the new async code drops coverage below 80%, add a focused async test for the uncovered branch (e.g. `AsyncSqlRepository.update`/`delete`/`delete_where`) in `libs/db/tests/`.

- [ ] **Step 2: Lint (ruff + mypy incl. libs/db)**

Run: `make lint`
Expected: green. Fix any mypy issues in the new async modules (annotate `async_sessionmaker[AsyncSession]` factory types).

- [ ] **Step 3: Manual event-loop check (the actual fix)**

Start the stack (`make dev` from the primary checkout, or `make run` + `make worker`), open several activity streams, and confirm the API stays responsive under load:
```bash
# with the app running on :8000, open 8 activity streams then time /health repeatedly
# (reuse the sse_probe approach from the freeze investigation)
```
Expected: `/health` latency stays flat with streams open (no intermittent multi-second stalls).

- [ ] **Step 4: Update docs**

Add `libs/db/` to the architecture tree in `CLAUDE.md`, and a one-line note that SSE streams use the async UoW while sync endpoints + the worker use the sync UoW. Add a `docs/project-history.md` line recording the async DB layer + SSE freeze fix.

- [ ] **Step 5: Commit docs**

```bash
git add docs/project-history.md CLAUDE.md
git commit -m "docs: record async DB layer + SSE event-loop freeze fix"
```

- [ ] **Step 6: Push + open PR**

```bash
git push -u origin feat/async-db-layer
gh pr create --base main --head feat/async-db-layer \
  --title "feat: async DB layer (libs/db) — unblock the SSE event-loop freeze" \
  --body "<summary + test plan: links the freeze diagnosis, describes libs/db sync+async split, the two SSE streams now async, aiosqlite tests + Postgres smoke>"
```

---

## Self-Review

**Spec coverage:**
- `libs/db` generic sync+async machinery → Tasks 2–4. ✔
- Domain-purity exception binding → Task 2 (Step 5, 8) + Task 5 (Step 3). ✔
- Async engine/session on same psycopg URL → Task 3. ✔
- `get_async_uow` + async engine on app.state + lifespan dispose → Task 6. ✔
- Both SSE streams (activity + run events) async + `is_disconnected()` → Tasks 7–8. ✔
- Minimal concretes (AgentEvent + RunEvent async) → Task 5. ✔
- Testing: aiosqlite mirror + Postgres smoke → Tasks 2,4,5,7. ✔
- Deps (sqlalchemy[asyncio], greenlet, aiosqlite, pytest-asyncio) + workspace → Task 1. ✔

**Placeholder scan:** The `_apply_filters` bodies in Tasks 2 & 4 say "copy verbatim" rather than re-pasting the 20-line block — this is a deliberate DRY pointer to a single source (`adapters/database/repository.py:39-60`), not a TBD. All other steps carry full code.

**Type consistency:** `AsyncUnitOfWork.agent_events` → `AsyncAgentEventRepository` (Task 5) matches its use in Task 7; `.run_events` → `AsyncRunEventRepository` matches Task 8. `get_async_uow` signature (Task 6) matches its consumers. `build_async_engine`/`build_async_session_factory` names consistent across Tasks 3,5,6,7.

**Known follow-ups (out of scope, noted for the PR):** the shared in-memory sqlite wiring for SSE tests (Task 7 Step 1) is the fiddliest part; if `cache=shared` proves flaky under the test driver, fall back to the Postgres smoke test as the integration signal and keep the sqlite tests at the repository/UoW level only.
