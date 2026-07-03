# Move Bus SQL into a Repository (UoW Pattern) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all SQLAlchemy from the bus adapter — move it into a `BusMessageRepository` and make `SqlMessageBus` a thin `MessageBus`-port delegator through the UnitOfWork. Pure refactor, no behavior change.

**Architecture:** `BusMessageRepository` (in `adapters/database`, cross-owner / not owner-scoped) owns `publish`/`claim_next(roles)`/`ack` + the row↔`AgentMessage` mapping; the UoW exposes it as `uow.bus_messages`; `SqlMessageBus(uow)` delegates; `build_message_bus(uow)` (was `(session)`) and its 3 call sites pass the UoW.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (sync), Celery, Postgres/SQLite, pytest.

## Global Constraints

- **No behavior change** — this is a refactor. `SKIP LOCKED` (non-sqlite) + busy-recipient exclusion + role filter + one-in-flight-per-recipient are all preserved byte-for-byte.
- **The bus is a cross-owner work queue.** `BusMessageRepository` must **NOT** apply owner-scoping — `claim_next` scans pending messages across all owners (the subscription engine drains it with an unscoped UoW). It accepts a `required_filters` kwarg for `UnitOfWork._repo()` uniformity but **ignores** it. Precedent: `SubscriberCursorRepository`.
- **No SQLAlchemy left in `adapters/bus/`** — the adapter imports no `select`/ORM/`Session`-query code. Acceptance: `grep -rn "select\|BusMessageRow\|with_for_update\|session\." projects/server/src/adapters/bus` returns nothing.
- **`MessageBus` port signature is unchanged** (`publish`/`claim_next(roles=None)`/`ack`).
- **Persistence isolation:** all SQL lives in `adapters/database`. Immutability. TDD. `make coverage` (80%) + `make lint` green.

---

## File Structure

- Modify `projects/server/src/adapters/database/repositories.py` — add `BusMessageRepository`.
- Modify `projects/server/src/adapters/database/uow.py` — add `bus_messages` property.
- Modify `projects/server/src/adapters/bus/sql.py` — gut `SqlMessageBus` to delegate (no SQL).
- Modify `projects/server/src/adapters/bus/factory.py` — `build_message_bus(uow)`.
- Modify `projects/server/src/interactors/api/deps.py` — `get_bus` passes `uow`.
- Modify `projects/server/src/interactors/worker/subscription_runner.py` — `ctx_factory` passes `uow`.
- Modify `projects/server/src/interactors/worker/bus_source.py` — pass `uow` to `build_message_bus`.
- Modify `projects/server/src/adapters/database/orm.py` — fix the `BusMessageRow` comment (line ~120).
- Create `projects/server/tests/adapters/database/test_bus_message_repository.py`.
- Modify `projects/server/tests/adapters/bus/test_sql_bus.py` — becomes a delegation test.
- Modify `projects/server/tests/interactors/worker/test_bus_source.py` — construct via UoW.

---

## Task 1: `BusMessageRepository` + `uow.bus_messages`

**Files:**
- Modify: `projects/server/src/adapters/database/repositories.py` (add the class; ensure `select`, `utcnow`, `AgentMessage`/`MessageStatus`/`MessageType`, `BusMessageRow` are imported)
- Modify: `projects/server/src/adapters/database/uow.py` (import + `bus_messages` property)
- Test: `projects/server/tests/adapters/database/test_bus_message_repository.py`

**Interfaces:**
- Consumes: `BusMessageRow` (orm), `AgentMessage`/`MessageStatus`/`MessageType` (domain), `SqlUnitOfWork._repo`.
- Produces: `BusMessageRepository(session, required_filters=None)` with `publish(msg)`, `claim_next(roles=None) -> AgentMessage | None`, `ack(msg)`, `_to_msg(row)` — cross-owner (ignores `required_filters`). `uow.bus_messages -> BusMessageRepository`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/database/test_bus_message_repository.py
import pytest
from adapters.database.orm import Base
from adapters.database.repositories import BusMessageRepository
from domain.runs.messages import AgentMessage, MessageStatus, MessageType, recipient_key
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def _pub(repo, role, owner="u1"):
    repo.publish(AgentMessage(owner_id=owner, run_id="r1",
        recipient=recipient_key("r1", role), role=role, type=MessageType.START))


def test_publish_claim_ack_round_trip(session):
    repo = BusMessageRepository(session)
    _pub(repo, "lead")
    claimed = repo.claim_next()
    assert claimed is not None and claimed.role == "lead"
    repo.ack(claimed)
    assert repo.claim_next() is None  # acked (done), nothing pending


def test_claim_next_filters_by_role(session):
    repo = BusMessageRepository(session)
    _pub(repo, "lead")
    _pub(repo, "engineer")
    assert repo.claim_next(["engineer"]).role == "engineer"


def test_claim_next_is_cross_owner(session):
    # a repo built with an owner filter still claims other owners' messages
    repo = BusMessageRepository(session, required_filters={"owner_id": "u2"})
    _pub(repo, "lead", owner="u1")
    assert repo.claim_next() is not None  # NOT owner-scoped


def test_busy_recipient_excluded(session):
    repo = BusMessageRepository(session)
    _pub(repo, "lead"); _pub(repo, "lead")  # same recipient run:r1:lead
    first = repo.claim_next()
    assert first is not None
    # second message for the same recipient is blocked while the first is claimed
    assert repo.claim_next() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_bus_message_repository.py -v`
Expected: FAIL — `BusMessageRepository` does not exist.

- [ ] **Step 3: Add `BusMessageRepository`**

In `repositories.py` (add missing imports as needed: `from domain.base import utcnow`, `from domain.runs.messages import AgentMessage, MessageStatus, MessageType`, `from adapters.database.orm import BusMessageRow`, and `select` from sqlalchemy):

```python
class BusMessageRepository:
    """Cross-owner work-queue repository for bus messages.

    NOT owner-scoped: the worker claims pending messages across ALL owners, so
    claim_next must not filter by owner. `required_filters` is accepted only so the
    UnitOfWork._repo() helper can build it uniformly — it is deliberately ignored.
    (Same shape as SubscriberCursorRepository.)
    """

    def __init__(self, session: Session, required_filters: dict | None = None) -> None:
        self.session = session

    def publish(self, msg: AgentMessage) -> None:
        self.session.add(BusMessageRow(
            id=msg.id, owner_id=msg.owner_id, run_id=msg.run_id, recipient=msg.recipient,
            role=msg.role, type=msg.type.value, payload=msg.payload, status=msg.status.value,
        ))
        self.session.flush()

    def claim_next(self, roles: list[str] | None = None) -> AgentMessage | None:
        busy = select(BusMessageRow.recipient).where(BusMessageRow.status == "claimed")
        q = select(BusMessageRow).where(
            BusMessageRow.status == "pending", BusMessageRow.recipient.notin_(busy)
        )
        if roles:
            q = q.where(BusMessageRow.role.in_(roles))
        q = q.order_by(BusMessageRow.created_at).limit(1)
        if self.session.get_bind().dialect.name != "sqlite":
            q = q.with_for_update(skip_locked=True)
        row = self.session.execute(q).scalar_one_or_none()
        if row is None:
            return None
        row.status = "claimed"
        row.claimed_at = utcnow()
        self.session.flush()
        return self._to_msg(row)

    def ack(self, msg: AgentMessage) -> None:
        row = self.session.get(BusMessageRow, msg.id)
        if row is None:
            raise RuntimeError(f"ack: message {msg.id} not found")
        row.status = MessageStatus.DONE.value
        self.session.flush()

    def _to_msg(self, row: BusMessageRow) -> AgentMessage:
        return AgentMessage(id=row.id, owner_id=row.owner_id, run_id=row.run_id,
                            recipient=row.recipient, role=row.role, type=MessageType(row.type),
                            payload=row.payload, status=MessageStatus(row.status),
                            created_at=row.created_at, claimed_at=row.claimed_at)
```

- [ ] **Step 4: Add the `bus_messages` UoW property**

In `uow.py`, add `BusMessageRepository` to the `from adapters.database.repositories import (...)` block, then:

```python
    @property
    def bus_messages(self) -> BusMessageRepository:
        return self._repo("bus_messages", BusMessageRepository)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_bus_message_repository.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/adapters/database/repositories.py projects/server/src/adapters/database/uow.py projects/server/tests/adapters/database/test_bus_message_repository.py
git commit -m "feat: BusMessageRepository (cross-owner bus SQL) + uow.bus_messages"
```

---

## Task 2: `SqlMessageBus` delegates via the UoW; rewire callers; remove bus SQL

**Files:**
- Modify: `projects/server/src/adapters/bus/sql.py` (gut to delegate)
- Modify: `projects/server/src/adapters/bus/factory.py` (`build_message_bus(uow)`)
- Modify: `projects/server/src/interactors/api/deps.py`, `projects/server/src/interactors/worker/subscription_runner.py`, `projects/server/src/interactors/worker/bus_source.py` (pass `uow`)
- Modify: `projects/server/src/adapters/database/orm.py` (fix the `BusMessageRow` comment)
- Test: `projects/server/tests/adapters/bus/test_sql_bus.py` (delegation), `projects/server/tests/interactors/worker/test_bus_source.py` (construct via UoW)

**Interfaces:**
- Consumes: `uow.bus_messages` (Task 1).
- Produces: `SqlMessageBus(uow)` (no SQL) implementing `MessageBus`; `build_message_bus(uow: SqlUnitOfWork) -> MessageBus`.

- [ ] **Step 1: Rewrite the `test_sql_bus.py` as a delegation test (RED)**

Replace the SQL-level tests (now covered by the repository test) with an adapter-delegation test that builds a real `SqlUnitOfWork` and drives publish→claim→ack through `SqlMessageBus`:

```python
# projects/server/tests/adapters/bus/test_sql_bus.py
import pytest
from adapters.bus.factory import build_message_bus
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_bus_adapter_delegates_publish_claim_ack(session_factory):
    uow = SqlUnitOfWork(session_factory)
    with uow.transaction():
        bus = build_message_bus(uow)
        bus.publish(AgentMessage(owner_id="u1", run_id="r1",
            recipient=recipient_key("r1", "lead"), role="lead", type=MessageType.START))
        claimed = bus.claim_next(["lead"])
        assert claimed is not None and claimed.role == "lead"
        bus.ack(claimed)
        assert bus.claim_next() is None
```

Run: `cd projects/server && uv run pytest tests/adapters/bus/test_sql_bus.py -v`
Expected: FAIL — `build_message_bus(uow)` currently takes a session; `SqlMessageBus` still expects a session.

- [ ] **Step 2: Gut `SqlMessageBus` to delegate (`sql.py`)**

```python
from typing import TYPE_CHECKING

from domain.runs.messages import AgentMessage

if TYPE_CHECKING:
    from adapters.database.uow import SqlUnitOfWork


class SqlMessageBus:
    """MessageBus port adapter — delegates to the UoW's bus_messages repository.

    Contains no SQL: all persistence lives in adapters/database BusMessageRepository.
    """

    def __init__(self, uow: "SqlUnitOfWork") -> None:
        self._uow = uow

    def publish(self, msg: AgentMessage) -> None:
        self._uow.bus_messages.publish(msg)

    def claim_next(self, roles: list[str] | None = None) -> AgentMessage | None:
        return self._uow.bus_messages.claim_next(roles)

    def ack(self, msg: AgentMessage) -> None:
        self._uow.bus_messages.ack(msg)
```

- [ ] **Step 3: `build_message_bus(uow)` (`factory.py`)**

```python
from typing import TYPE_CHECKING

from adapters.bus.ports import MessageBus
from adapters.bus.sql import SqlMessageBus

if TYPE_CHECKING:
    from adapters.database.uow import SqlUnitOfWork


def build_message_bus(uow: "SqlUnitOfWork") -> MessageBus:
    """Factory for the active MessageBus implementation.
    Swap this to change the queue backend (Redis, RabbitMQ, etc.)."""
    return SqlMessageBus(uow)
```

- [ ] **Step 4: Update the 3 call sites to pass `uow`**

- `interactors/api/deps.py::get_bus` — `return build_message_bus(uow)` (was `uow.session`).
- `interactors/worker/subscription_runner.py::ctx_factory` — `bus=build_message_bus(uow),` (was `uow.session`).
- `interactors/worker/bus_source.py` — `fetch_next`/`advance`/`on_poison` build the bus from the `uow` they already receive/create: `build_message_bus(uow)` (was `build_message_bus(uow.session)`).

- [ ] **Step 5: Fix the `orm.py` comment**

In `orm.py`, the comment above `BusMessageRow` currently reads *"accessed directly by the SqlMessageBus adapter, not via a UoW repository"*. Replace with:
`# persisted via BusMessageRepository (adapters/database); the SqlMessageBus adapter delegates to uow.bus_messages`

- [ ] **Step 6: Update `test_bus_source.py` construction**

That test currently publishes via `build_message_bus(<session>).publish(...)` / `build_message_bus(s2).claim_next()`. Change each to build a `SqlUnitOfWork(session_factory)` and call `build_message_bus(uow)` inside a `uow.transaction()` (or publish via `uow.bus_messages.publish(...)`). Keep the assertions identical — the `BusSource(roles)` behavior is unchanged.

- [ ] **Step 7: Run tests + grep-proof**

Run: `cd projects/server && uv run pytest tests/adapters/bus tests/interactors/worker tests/api -q`
Expected: PASS (delegation + bus_source + api tests).
Run: `cd projects/server && uv run pytest -q`
Expected: full suite PASS.
Run: `grep -rn "select\|BusMessageRow\|with_for_update\|session\." projects/server/src/adapters/bus`
Expected: **no matches** (no SQL left in the bus adapter).

- [ ] **Step 8: Commit**

```bash
git add projects/server/src/adapters/bus/ projects/server/src/interactors/api/deps.py projects/server/src/interactors/worker/subscription_runner.py projects/server/src/interactors/worker/bus_source.py projects/server/src/adapters/database/orm.py projects/server/tests/adapters/bus/test_sql_bus.py projects/server/tests/interactors/worker/test_bus_source.py
git commit -m "refactor: SqlMessageBus delegates to uow.bus_messages; no SQL in bus adapter"
```

---

## Task 3: Gates + docs

**Files:**
- Modify: `docs/architecture.md` (if it lists the bus adapter as an SQL exception) + `docs/project-history.md`

- [ ] **Step 1: Backend gate**

Run: `cd /Users/noel/projects/naaf/.worktrees/bus-repository && make coverage && make lint`
Expected: coverage ≥80%, ruff + mypy clean.

- [ ] **Step 2: Docs**

- If `docs/architecture.md` documents "SQL only in adapters/database repositories" with the bus as a known exception, remove that caveat (it's now compliant).
- Add a one-line note to `docs/project-history.md`: the bus SQL was moved into `BusMessageRepository` (cross-owner) and `SqlMessageBus` now delegates via `uow.bus_messages` — the last SQL-in-an-adapter exception is closed.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md docs/project-history.md
git commit -m "docs: bus adapter now SQL-free (BusMessageRepository)"
```

---

## Self-Review Notes (author)

- **Spec coverage:** SQL moved to `BusMessageRepository` (T1) ✓; cross-owner / not owner-scoped, with `required_filters` accepted-but-ignored + a test proving cross-owner claim (T1) ✓; `uow.bus_messages` (T1) ✓; `SqlMessageBus` thin delegator, no SQL (T2) + grep-proof (T2 step 7) ✓; `build_message_bus(uow)` + 3 call sites (T2) ✓; `orm.py` comment fixed (T2) ✓; behavior unchanged — the moved SQL is byte-identical (T1 step 3 is the current adapter code verbatim) ✓.
- **Type consistency:** `claim_next(roles: list[str] | None = None)` identical across `MessageBus` port → `SqlMessageBus` → `BusMessageRepository`. `build_message_bus(uow)` consumed identically at all 3 call sites.
- **No behavior change:** the `claim_next` query (busy-exclusion, role filter, ordering, `SKIP LOCKED`) is copied verbatim into the repository; `publish`/`ack` unchanged; transaction/session sharing preserved (the repo uses the UoW's session).
- **Known softness:** T2 step 6 (test_bus_source construction) is described rather than fully verbatim because it depends on that file's current fixtures; the full suite is the gate. Circular-import safety: `bus/sql.py` + `bus/factory.py` reference `SqlUnitOfWork` only under `TYPE_CHECKING`, so no runtime import cycle (bus → database).
