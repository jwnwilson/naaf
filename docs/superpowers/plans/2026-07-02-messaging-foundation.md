# Messaging Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conversational message store + `/threads` read/send API and wire the UI inbox and sidebar chat to it as two views of the same live data.

**Architecture:** A new conversational `Message` domain (separate from the orchestration `bus_messages`), persisted via a `messages` table with an owner-scoped `MessageRepository`. A **thread is a run** (1:1) — `GET /threads` projects owner-scoped runs into the UI's `Thread` shape; `GET/POST /threads/{id}/messages` read and append messages. The UI inbox (left list → `/threads`, conversation pane → messages + live compose) and sidebar `ChatPanel` consume one shared set of React Query hooks. Sending **persists only** — no bus publish yet.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), Alembic, Postgres/SQLite, pytest. React 18, TypeScript (strict), @tanstack/react-query v5, MSW v2, vitest, pnpm.

## Global Constraints

- **Immutability:** update Pydantic models via `model_copy(update={...})`; never mutate. React state updated immutably.
- **API envelope:** every response is `{success, data, error}` (+ `meta` for pagination). Use `ok(...)` and `Envelope[...]` from `crud_router`.
- **camelCase contract:** `*Out`/`*In` models use camelCase field names that ARE the JSON keys (no aliases). Existing `Thread`/`Message` UI schemas are the target shape.
- **Owner scoping:** every owned row carries `owner_id`; the UnitOfWork applies it as a required filter on every query. Cross-owner reads return 404.
- **Persistence isolation:** ALL SQLAlchemy `select`/ORM access lives in `adapters/database` repositories — never in domain, interactors, or routes.
- **IDs:** 32-char UUID hex (`new_id()`); timestamps rendered with `iso(...)` (ISO-8601).
- **TDD:** write the failing test first; AAA structure; descriptive behaviour names. `make coverage` 80% gate and `make lint` must pass before PR.
- **Package managers:** backend `uv`; UI `pnpm` (never npm). Backend commands run from `projects/server`; UI from `projects/ui`.
- **Non-goals (do NOT build):** agents producing chat; chat→bus bridge on send (persist only); new-message→notification alerts; attachments; threads not tied to a run.

---

## File Structure

**Backend (`projects/server/src`):**
- Create `domain/messaging/message.py` — `MessageRole` enum + `Message` entity.
- Create `domain/messaging/thread.py` — `ThreadView` + pure `thread_from_run(run)` projection.
- Modify `adapters/database/orm.py` — add `MessageRow`.
- Modify `adapters/database/repositories.py` — add `MessageRepository`.
- Modify `adapters/database/uow.py` — add `messages` property.
- Modify `adapters/database/ports.py` — add `messages` to `UnitOfWork` protocol.
- Create `adapters/database/migrations/versions/0007_messages.py` — `messages` table.
- Modify `interactors/api/contract.py` — add `ThreadOut`, `MessageOut`, `MessageCreate`.
- Create `interactors/api/routes/threads.py` — the three endpoints.
- Modify `interactors/api/routes/__init__.py` — register the threads router.
- Tests: `tests/domain/messaging/test_message_model.py`, `tests/domain/messaging/test_thread_projection.py`, `tests/adapters/database/test_message_repository.py`, `tests/adapters/database/test_migrations.py` (add a case), `tests/api/test_threads_api.py`.

**Frontend (`projects/ui/src`):**
- Modify `lib/api/schema.d.ts` — remove `InboxItem` + inbox operations (Thread/Message already match).
- Modify `lib/api/queryKeys.ts` — add `threadMessages`.
- Create `lib/api/hooks/useThreadMessages.ts`, `lib/api/hooks/useSendMessage.ts`.
- Modify `lib/api/hooks/index.ts` — export the new hooks.
- Modify `app/ChatPanel.tsx` — use shared hooks + live send.
- Modify `modules/inbox/InboxScreen.tsx`, `modules/inbox/InboxList.tsx`, `modules/inbox/NotificationItem.tsx`, `modules/inbox/ConversationPane.tsx` — thread-based list + live compose.
- Delete `lib/api/hooks/useInbox.ts`, `modules/inbox/useInboxConversation.ts` (after nothing consumes them).
- Modify `lib/api/mocks/handlers.ts` — move `/threads` handlers to `liveHandlers`, remove `/inbox` handlers.
- Modify `lib/api/mocks/db.ts` + fixtures — drop `inboxItems`.
- Tests co-located `*.test.tsx` / `*.test.ts` alongside each changed file.

---

## Task 1: `Message` domain model

**Files:**
- Create: `projects/server/src/domain/messaging/message.py`
- Test: `projects/server/tests/domain/messaging/test_message_model.py`

**Interfaces:**
- Produces: `MessageRole` (StrEnum: `USER="user"`, `AGENT="agent"`, `LEAD_AGENT="lead_agent"`); `Message(Entity)` with fields `owner_id: str`, `thread_id: str`, `role: MessageRole`, `content: str`, `agent_id: str | None = None` (plus `id/created_at/updated_at` from `Entity`).

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/domain/messaging/test_message_model.py
from domain.messaging.message import Message, MessageRole


def test_message_defaults_id_and_optional_agent():
    msg = Message(owner_id="u1", thread_id="r1", role=MessageRole.USER, content="hi")
    assert len(msg.id) == 32
    assert msg.agent_id is None
    assert msg.role == "user"


def test_message_is_immutable_via_model_copy():
    msg = Message(owner_id="u1", thread_id="r1", role=MessageRole.USER, content="hi")
    updated = msg.model_copy(update={"content": "bye"})
    assert msg.content == "hi"
    assert updated.content == "bye"


def test_role_values():
    assert [r.value for r in MessageRole] == ["user", "agent", "lead_agent"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_message_model.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.messaging.message`.

- [ ] **Step 3: Write minimal implementation**

```python
# projects/server/src/domain/messaging/message.py
from enum import StrEnum

from domain.base import Entity


class MessageRole(StrEnum):
    USER = "user"
    AGENT = "agent"
    LEAD_AGENT = "lead_agent"


class Message(Entity):
    owner_id: str
    thread_id: str  # == run_id
    role: MessageRole
    content: str
    agent_id: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_message_model.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/message.py projects/server/tests/domain/messaging/test_message_model.py
git commit -m "feat: add conversational Message domain model"
```

---

## Task 2: Thread projection (`run → ThreadView`)

**Files:**
- Create: `projects/server/src/domain/messaging/thread.py`
- Test: `projects/server/tests/domain/messaging/test_thread_projection.py`

**Interfaces:**
- Consumes: `Run` from `domain.runs.run` (fields `id`, `work_item_id`, `created_at`); `AgentRole` from `domain.team`.
- Produces: `THREAD_LEAD_ROLE: str` (`= "lead"`); `ThreadView(BaseModel)` with `id: str`, `agent_id: str`, `work_item_id: str`, `created_at: datetime | None`; `thread_from_run(run: Run) -> ThreadView`.

Rationale: a thread is a run 1:1. `agent_id` is the run's lead role — there is no per-run lead field on `Run`, so we use the documented constant `AgentRole.LEAD.value`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/domain/messaging/test_thread_projection.py
from datetime import UTC, datetime

from domain.messaging.thread import THREAD_LEAD_ROLE, ThreadView, thread_from_run
from domain.runs.run import Run


def _run() -> Run:
    return Run(
        id="a" * 32,
        owner_id="u1",
        work_item_id="w1",
        project_id="p1",
        autonomy_level="gated_all",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )


def test_thread_from_run_maps_fields():
    view = thread_from_run(_run())
    assert isinstance(view, ThreadView)
    assert view.id == "a" * 32
    assert view.work_item_id == "w1"
    assert view.created_at == datetime(2026, 7, 2, tzinfo=UTC)


def test_thread_agent_id_is_lead_role():
    assert thread_from_run(_run()).agent_id == THREAD_LEAD_ROLE
    assert THREAD_LEAD_ROLE == "lead"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_thread_projection.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.messaging.thread`.

- [ ] **Step 3: Write minimal implementation**

```python
# projects/server/src/domain/messaging/thread.py
from datetime import datetime

from pydantic import BaseModel

from domain.runs.run import Run
from domain.team import AgentRole

THREAD_LEAD_ROLE = AgentRole.LEAD.value  # "lead"


class ThreadView(BaseModel):
    id: str
    agent_id: str
    work_item_id: str
    created_at: datetime | None


def thread_from_run(run: Run) -> ThreadView:
    return ThreadView(
        id=run.id,
        agent_id=THREAD_LEAD_ROLE,
        work_item_id=run.work_item_id,
        created_at=run.created_at,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_thread_projection.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/thread.py projects/server/tests/domain/messaging/test_thread_projection.py
git commit -m "feat: add run->thread projection"
```

---

## Task 3: `MessageRow` ORM + `MessageRepository` + UoW wiring

**Files:**
- Modify: `projects/server/src/adapters/database/orm.py` (add `MessageRow` after `BusMessageRow`, ~line 127)
- Modify: `projects/server/src/adapters/database/repositories.py` (import `MessageRow` + `Message`; add `MessageRepository`)
- Modify: `projects/server/src/adapters/database/uow.py` (import `MessageRepository`; add `messages` property)
- Modify: `projects/server/src/adapters/database/ports.py` (add `messages` to `UnitOfWork` protocol)
- Test: `projects/server/tests/adapters/database/test_message_repository.py`

**Interfaces:**
- Consumes: `Message` (Task 1); `SqlRepository`, `SqlUnitOfWork`, `PaginatedResult`.
- Produces: `MessageRow` (table `messages`); `MessageRepository(SqlRepository[Message])`; `uow.messages` returning `MessageRepository`. Messages listed via `uow.messages.read_multi(filters={"thread_id": <id>}, order_by="created_at", page_size, page_number)` (oldest-first).

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/database/test_message_repository.py
from adapters.database.uow import SqlUnitOfWork
from domain.messaging.message import Message, MessageRole


def _uow(sf, owner="u1"):
    return SqlUnitOfWork(sf, required_filters={"owner_id": owner})


def test_message_round_trip_stamps_owner(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        m = uow.messages.create(
            Message(owner_id="", thread_id="r1", role=MessageRole.USER, content="hello")
        )
        got = uow.messages.read(m.id)
    assert got.owner_id == "u1"
    assert got.content == "hello"
    assert got.role == "user"


def test_messages_list_by_thread_oldest_first(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        for text in ("first", "second", "third"):
            uow.messages.create(
                Message(owner_id="", thread_id="r1", role=MessageRole.USER, content=text)
            )
        uow.messages.create(
            Message(owner_id="", thread_id="OTHER", role=MessageRole.USER, content="nope")
        )
        page = uow.messages.read_multi(filters={"thread_id": "r1"}, order_by="created_at")
    assert [m.content for m in page.results] == ["first", "second", "third"]
    assert page.total == 3


def test_messages_are_owner_scoped(session_factory):
    with _uow(session_factory, "u1").transaction() as uow:
        uow.messages.create(
            Message(owner_id="", thread_id="r1", role=MessageRole.USER, content="mine")
        )
    with _uow(session_factory, "u2").transaction() as uow:
        page = uow.messages.read_multi(filters={"thread_id": "r1"})
    assert page.results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_message_repository.py -v`
Expected: FAIL — `AttributeError: 'SqlUnitOfWork' object has no attribute 'messages'`.

- [ ] **Step 3a: Add `MessageRow` to `orm.py`**

Add after `BusMessageRow` (after line 127), and ensure `Index` and `Text` are available — `Index` must be added to the existing `from sqlalchemy import ...` line:

```python
class MessageRow(_Timestamped, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_owner_thread", "owner_id", "thread_id"),)
    thread_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
```

Update the imports line at the top of `orm.py` (currently `from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint`) to include `Index`:

```python
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
```

- [ ] **Step 3b: Add `MessageRepository` to `repositories.py`**

Add `Message` to the domain imports and `MessageRow` to the orm imports, then add the class near `NotificationRepository`:

```python
# add to imports
from domain.messaging.message import Message
# ... and add MessageRow to the `from adapters.database.orm import (...)` block

class MessageRepository(SqlRepository[Message]):
    orm_model = MessageRow
    dto = Message
```

- [ ] **Step 3c: Wire `messages` into `uow.py`**

Add `MessageRepository` to the `from adapters.database.repositories import (...)` block, then add the property:

```python
    @property
    def messages(self) -> MessageRepository:
        return self._repo("messages", MessageRepository)
```

- [ ] **Step 3d: Add `messages` to the `UnitOfWork` protocol in `ports.py`**

After the `notifications` property in the `UnitOfWork` Protocol:

```python
    @property
    def messages(self) -> Repository: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_message_repository.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/orm.py projects/server/src/adapters/database/repositories.py projects/server/src/adapters/database/uow.py projects/server/src/adapters/database/ports.py projects/server/tests/adapters/database/test_message_repository.py
git commit -m "feat: add messages table, repository, and uow wiring"
```

---

## Task 4: Alembic migration for `messages`

**Files:**
- Create: `projects/server/src/adapters/database/migrations/versions/0007_messages.py`
- Modify: `projects/server/tests/adapters/database/test_migrations.py` (add one test)

**Interfaces:**
- Consumes: prior head `0006_notifications`.
- Produces: `messages` table with columns `id, owner_id, thread_id, role, agent_id, content, created_at, updated_at`; indexes `ix_messages_owner_id`, `ix_messages_thread_id`, `ix_messages_owner_thread`.

- [ ] **Step 1: Write the failing test**

Add to `projects/server/tests/adapters/database/test_migrations.py`:

```python
def test_migration_creates_messages(tmp_path):
    import os
    import sqlite3
    import subprocess
    from pathlib import Path

    db = tmp_path / "naaf.db"
    server = Path(__file__).resolve().parents[2]
    env = {"naaf_db_url": f"sqlite:///{db}", "PATH": os.environ["PATH"]}
    r = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=server, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db)
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "messages" in tables
    cols = {r[1] for r in con.execute("PRAGMA table_info(messages)")}
    assert {"id", "owner_id", "thread_id", "role", "agent_id", "content"} <= cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_migrations.py::test_migration_creates_messages -v`
Expected: FAIL — `messages` not in tables (assertion error).

- [ ] **Step 3: Write the migration**

```python
# projects/server/src/adapters/database/migrations/versions/0007_messages.py
"""messages

Revision ID: 0007_messages
Revises: 0006_notifications
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_messages"
down_revision = "0006_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("thread_id", sa.String(32), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=True),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_owner_id"), "messages", ["owner_id"], unique=False)
    op.create_index(op.f("ix_messages_thread_id"), "messages", ["thread_id"], unique=False)
    op.create_index("ix_messages_owner_thread", "messages", ["owner_id", "thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_owner_thread", table_name="messages")
    op.drop_index(op.f("ix_messages_thread_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_owner_id"), table_name="messages")
    op.drop_table("messages")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_migrations.py -v`
Expected: PASS (all migration tests, including the new one).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/migrations/versions/0007_messages.py projects/server/tests/adapters/database/test_migrations.py
git commit -m "feat: add messages table migration"
```

---

## Task 5: `/threads` contract + routes

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py` (add `ThreadOut`, `MessageOut`, `MessageCreate` at end)
- Create: `projects/server/src/interactors/api/routes/threads.py`
- Modify: `projects/server/src/interactors/api/routes/__init__.py` (register router)
- Test: `projects/server/tests/api/test_threads_api.py`

**Interfaces:**
- Consumes: `Message`, `MessageRole` (Task 1); `thread_from_run` (Task 2); `uow.runs`, `uow.messages`; `iso`, `Envelope`, `ok`, `get_uow`.
- Produces: `GET /threads`, `GET /threads/{id}/messages`, `POST /threads/{id}/messages` (201). `ThreadOut{id, agentId, workItemId, createdAt}`, `MessageOut{id, conversationId, role, agentId, content, createdAt}`, `MessageCreate{content, agentId?}`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/api/test_threads_api.py
from adapters.database.uow import SqlUnitOfWork
from domain.runs.run import Run


def _make_run(session_factory, owner="dev-user", wid="w1") -> str:
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction():
        run = uow.runs.create(
            Run(owner_id="", work_item_id=wid, project_id="p1", autonomy_level="gated_all")
        )
    return run.id


def test_list_threads_projects_runs(client, session_factory):
    run_id = _make_run(session_factory)
    body = client.get("/threads").json()
    assert body["success"]
    row = next(t for t in body["data"] if t["id"] == run_id)
    assert row["agentId"] == "lead"
    assert row["workItemId"] == "w1"
    assert "owner_id" not in row


def test_post_then_list_messages_oldest_first(client, session_factory):
    run_id = _make_run(session_factory)
    client.post(f"/threads/{run_id}/messages", json={"content": "first"})
    client.post(f"/threads/{run_id}/messages", json={"content": "second"})
    body = client.get(f"/threads/{run_id}/messages").json()
    assert body["success"]
    assert [m["content"] for m in body["data"]] == ["first", "second"]
    assert body["data"][0]["role"] == "user"
    assert body["data"][0]["conversationId"] == run_id


def test_post_message_returns_201_and_created(client, session_factory):
    run_id = _make_run(session_factory)
    res = client.post(f"/threads/{run_id}/messages", json={"content": "hi", "agentId": "lead"})
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["content"] == "hi"
    assert data["agentId"] == "lead"
    assert data["role"] == "user"


def test_empty_content_is_rejected(client, session_factory):
    run_id = _make_run(session_factory)
    res = client.post(f"/threads/{run_id}/messages", json={"content": "   "})
    assert res.status_code == 422


def test_foreign_thread_is_404(client, session_factory):
    # a run owned by someone else
    other_run = _make_run(session_factory, owner="someone-else", wid="w9")
    assert client.get(f"/threads/{other_run}/messages").status_code == 404
    assert client.post(f"/threads/{other_run}/messages", json={"content": "x"}).status_code == 404


def test_messages_do_not_touch_the_bus(client, session_factory):
    run_id = _make_run(session_factory)
    client.post(f"/threads/{run_id}/messages", json={"content": "hi"})
    # persist-only: no bus_messages row was written by the chat send
    from sqlalchemy import text
    with session_factory() as s:
        count = s.execute(text("SELECT COUNT(*) FROM bus_messages")).scalar_one()
    assert count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py -v`
Expected: FAIL — 404 for `/threads` (router not registered).

- [ ] **Step 3a: Add contract models to `contract.py`**

At the end of `projects/server/src/interactors/api/contract.py` (ensure `field_validator` is imported from pydantic — extend the existing `from pydantic import BaseModel, ConfigDict` line to `from pydantic import BaseModel, ConfigDict, field_validator`):

```python
# ---------------------------------------------------------------------------
# Messaging (threads)
# ---------------------------------------------------------------------------


class ThreadOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    agentId: str
    workItemId: str
    createdAt: str


class MessageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    conversationId: str
    role: str  # MessageRole value
    agentId: str | None = None
    content: str
    createdAt: str


class MessageCreate(BaseModel):
    content: str
    agentId: str | None = None

    @field_validator("content")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v
```

- [ ] **Step 3b: Create `routes/threads.py`**

```python
# projects/server/src/interactors/api/routes/threads.py
from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from fastapi import APIRouter, Depends

from domain.messaging.message import Message, MessageRole
from domain.messaging.thread import thread_from_run
from interactors.api.contract import MessageCreate, MessageOut, ThreadOut, iso
from interactors.api.deps import get_uow

router = APIRouter(prefix="/threads", tags=["threads"])


def _thread_out(view) -> ThreadOut:
    return ThreadOut(
        id=view.id,
        agentId=view.agent_id,
        workItemId=view.work_item_id,
        createdAt=iso(view.created_at),
    )


def _message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        conversationId=m.thread_id,
        role=m.role,
        agentId=m.agent_id,
        content=m.content,
        createdAt=iso(m.created_at),
    )


def _page_meta(page) -> dict:
    return {
        "total": page.total,
        "page_size": page.page_size,
        "page_number": page.page_number,
    }


@router.get("", response_model=Envelope[list[ThreadOut]])
def list_threads(
    page_size: int = 50,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    page = uow.runs.read_multi(
        page_size=page_size, page_number=page_number, order_by="-created_at"
    )
    return ok(
        [_thread_out(thread_from_run(r)) for r in page.results],
        meta=_page_meta(page),
    )


@router.get("/{id}/messages", response_model=Envelope[list[MessageOut]])
def list_messages(
    id: UUID,
    page_size: int = 50,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    uow.runs.read(id.hex)  # 404 if the run/thread is not the caller's
    page = uow.messages.read_multi(
        filters={"thread_id": id.hex},
        page_size=page_size,
        page_number=page_number,
        order_by="created_at",
    )
    return ok([_message_out(m) for m in page.results], meta=_page_meta(page))


@router.post("/{id}/messages", status_code=201, response_model=Envelope[MessageOut])
def post_message(
    id: UUID,
    payload: MessageCreate,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    uow.runs.read(id.hex)  # 404 if the run/thread is not the caller's
    created = uow.messages.create(
        Message(
            owner_id="",
            thread_id=id.hex,
            role=MessageRole.USER,
            content=payload.content,
            agent_id=payload.agentId,
        )
    )
    return ok(_message_out(created))
```

- [ ] **Step 3c: Register the router in `routes/__init__.py`**

Add the import and the `include_router` call:

```python
from interactors.api.routes.threads import router as threads_router
# ... inside register_routers(app):
    app.include_router(threads_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/contract.py projects/server/src/interactors/api/routes/threads.py projects/server/src/interactors/api/routes/__init__.py projects/server/tests/api/test_threads_api.py
git commit -m "feat: add /threads read + send API"
```

- [ ] **Step 6: Full backend gate**

Run: `cd projects/server && make coverage && make lint`
Expected: coverage ≥80%, lint clean. Fix any fallout before moving to the UI.

---

## Task 6: Trim the UI contract (`schema.d.ts`)

**Files:**
- Modify: `projects/ui/src/lib/api/schema.d.ts`

The backend was shaped to the existing `Thread` and `Message` schemas, so **those already match** — no regeneration needed. This task only removes the now-dead `/inbox` mock contract.

**Interfaces:**
- Produces: `schema.d.ts` with no `InboxItem` schema and no `listInbox` / `getInboxItem` / `markInboxItemRead` / `markAllInboxRead` operations or their `/inbox*` path entries. `Thread`, `Message`, `Conversation` remain untouched.

- [ ] **Step 1: Remove the `InboxItem` schema block**

Delete the `InboxItem: { ... };` block (the `type: "action_needed" | "review_needed" | "info" | "resolved"` shape).

- [ ] **Step 2: Remove the inbox operations + paths**

Delete the `listInbox`, `getInboxItem`, `markInboxItemRead`, `markAllInboxRead` operation blocks and any `"/inbox"` / `"/inbox/{id}"` / `"/inbox/{id}/read"` / `"/inbox/mark-all-read"` entries in the `paths` map.

- [ ] **Step 3: Verify no dangling references + typecheck**

Run: `cd projects/ui && grep -rn "InboxItem\|listInbox\|/inbox" src/lib/api/schema.d.ts` → expect no matches.
Run: `cd projects/ui && pnpm exec tsc --noEmit`
Expected: type errors ONLY in files that still import `InboxItem` (`useInbox.ts`, `InboxList.tsx`, `ConversationPane.tsx`) — those are fixed in Tasks 8–9. No errors inside `schema.d.ts` itself.

- [ ] **Step 4: Commit**

```bash
git add projects/ui/src/lib/api/schema.d.ts
git commit -m "chore: remove dead /inbox contract from ui schema"
```

---

## Task 7: Shared thread-message hooks

**Files:**
- Modify: `projects/ui/src/lib/api/queryKeys.ts`
- Create: `projects/ui/src/lib/api/hooks/useThreadMessages.ts`
- Create: `projects/ui/src/lib/api/hooks/useSendMessage.ts`
- Modify: `projects/ui/src/lib/api/hooks/index.ts`
- Test: `projects/ui/src/lib/api/hooks/useSendMessage.test.tsx`

**Interfaces:**
- Consumes: `apiList`, `apiPost` from `../client`; `queryKeys`; `Message = components["schemas"]["Message"]`.
- Produces:
  - `queryKeys.threadMessages(threadId?: string)` → `["threads", threadId ?? "none", "messages"]`.
  - `useThreadMessages(threadId?: string)` → `UseQueryResult<Message[]>` (enabled only when `threadId` set; `select` maps `{results}` → `Message[]`).
  - `useSendMessage(threadId: string)` → `UseMutationResult` mutating `{content, agentId?}` via `POST /threads/{threadId}/messages`; optimistic append to `threadMessages(threadId)`, rollback on error, invalidate on settle.

- [ ] **Step 1: Add the query key**

In `projects/ui/src/lib/api/queryKeys.ts`, add inside the object:

```ts
  threadMessages: (threadId?: string) => ["threads", threadId ?? "none", "messages"] as const,
```

- [ ] **Step 2: Write the failing test**

```tsx
// projects/ui/src/lib/api/hooks/useSendMessage.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test } from "vitest";
import { useSendMessage } from "./useSendMessage";

const server = setupServer(
  http.post("/api/threads/r1/messages", async ({ request }) => {
    const body = (await request.json()) as { content: string };
    return HttpResponse.json(
      {
        success: true,
        error: null,
        data: {
          id: "m1",
          conversationId: "r1",
          role: "user",
          agentId: null,
          content: body.content,
          createdAt: "2026-07-02T00:00:00Z",
        },
      },
      { status: 201 },
    );
  }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("sends a message and resolves with the created message", async () => {
  const { result } = renderHook(() => useSendMessage("r1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ content: "hello" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.content).toBe("hello");
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/useSendMessage.test.tsx`
Expected: FAIL — cannot find module `./useSendMessage`.

- [ ] **Step 4: Write `useThreadMessages.ts`**

```ts
// projects/ui/src/lib/api/hooks/useThreadMessages.ts
import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Message = components["schemas"]["Message"];

export function useThreadMessages(threadId?: string) {
  return useQuery({
    queryKey: queryKeys.threadMessages(threadId),
    queryFn: () => apiList<Message>(`/threads/${threadId!}/messages`),
    enabled: Boolean(threadId),
    select: (page) => page.results,
  });
}
```

- [ ] **Step 5: Write `useSendMessage.ts`**

```ts
// projects/ui/src/lib/api/hooks/useSendMessage.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import type { Message } from "./useThreadMessages";

type SendVars = { content: string; agentId?: string | null };

export function useSendMessage(threadId: string) {
  const qc = useQueryClient();
  const key = queryKeys.threadMessages(threadId);
  return useMutation<Message, Error, SendVars, { previous?: { results: Message[] } }>({
    mutationFn: (vars) =>
      apiPost<Message>(`/threads/${threadId}/messages`, {
        content: vars.content,
        agentId: vars.agentId ?? null,
      }),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<{ results: Message[] }>(key);
      const optimistic: Message = {
        id: `optimistic-${vars.content}`,
        conversationId: threadId,
        role: "user",
        agentId: vars.agentId ?? null,
        content: vars.content,
        attachments: null,
        createdAt: new Date().toISOString(),
      };
      qc.setQueryData<{ results: Message[]; meta?: unknown }>(key, (old) =>
        old
          ? { ...old, results: [...old.results, optimistic] }
          : { results: [optimistic], meta: { total: 1, page_size: 50, page_number: 1 } },
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: key });
    },
  });
}
```

> Note: `useThreadMessages` returns `Message[]` via `select`, but the cache entry stored under `threadMessages(threadId)` holds the raw `{results, meta}` object (React Query caches the queryFn result, not the selected value). The optimistic update therefore reads/writes `{results}` — consistent with what `apiList` returns.

- [ ] **Step 6: Export from `hooks/index.ts`**

```ts
export { useThreadMessages } from "./useThreadMessages";
export type { Message } from "./useThreadMessages";
export { useSendMessage } from "./useSendMessage";
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/useSendMessage.test.tsx`
Expected: PASS (1 passed).

- [ ] **Step 8: Commit**

```bash
git add projects/ui/src/lib/api/queryKeys.ts projects/ui/src/lib/api/hooks/useThreadMessages.ts projects/ui/src/lib/api/hooks/useSendMessage.ts projects/ui/src/lib/api/hooks/index.ts projects/ui/src/lib/api/hooks/useSendMessage.test.tsx
git commit -m "feat: shared thread-message + send hooks"
```

---

## Task 8: Live sidebar `ChatPanel`

**Files:**
- Modify: `projects/ui/src/app/ChatPanel.tsx`
- Test: `projects/ui/src/app/ChatPanel.test.tsx` (extend)

**Interfaces:**
- Consumes: `useThreads` (existing), `useThreadMessages`, `useSendMessage` (Task 7).
- Produces: `ChatPanel` renders the first thread's messages via the shared hook and sends via `useSendMessage` (its `ChatInput` becomes a controlled, submitting input).

- [ ] **Step 1: Write the failing test**

Extend `ChatPanel.test.tsx` with a send test (MSW mocks `/threads` → one thread `{id:"r1", agentId:"lead", workItemId:"w1", createdAt}` and `/threads/r1/messages` GET `[]`, POST → created). Assert typing into the "Message…" input and clicking "send" issues the POST and the optimistic message appears:

```tsx
test("sends a message from the sidebar", async () => {
  renderChatPanel(); // existing helper with QueryClient + MSW
  const input = await screen.findByPlaceholderText("Message…");
  await userEvent.type(input, "ship it");
  await userEvent.click(screen.getByLabelText("send"));
  expect(await screen.findByText("ship it")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm exec vitest run src/app/ChatPanel.test.tsx`
Expected: FAIL — input is `readOnly`/inert; POST never issued; "ship it" not rendered.

- [ ] **Step 3: Rewire `ChatPanel.tsx`**

Replace the local `useThreadMessages` definition with the shared hook import, and make `ChatInput` live:

```tsx
// top of file
import { useThreads, useThreadMessages, useSendMessage } from "../lib/api/hooks";
// remove the local `useThreadMessages` function and the now-unused apiFetch/useQuery imports
```

Replace `ChatInput` with a controlled form bound to the active thread:

```tsx
function ChatInput({ threadId }: { threadId: string | undefined }) {
  const [value, setValue] = useState("");
  const send = useSendMessage(threadId ?? "");
  const disabled = !threadId || value.trim().length === 0;

  function submit() {
    if (disabled) return;
    send.mutate({ content: value.trim() });
    setValue("");
  }

  return (
    <div className="p-[13px]">
      <form
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        className="rounded-[7px] border border-[rgba(255,255,255,0.09)] bg-[#101316] p-2"
      >
        <div className="flex items-center gap-1 pb-2">
          <span className="rounded-[3px] border border-[rgba(255,255,255,0.08)] px-1.5 py-0.5 font-mono text-[9.5px] text-[#3a3d44]">
            @agent
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Message…"
            className="flex-1 bg-transparent text-[11.5px] text-[#c4c5cb] placeholder-[#20222a] outline-none"
          />
          <button
            type="submit"
            aria-label="send"
            disabled={disabled}
            className="flex h-[22px] w-[22px] items-center justify-center rounded-[5px] bg-[rgba(124,108,240,0.18)] text-accent disabled:opacity-40"
          >
            ↑
          </button>
        </div>
      </form>
    </div>
  );
}
```

In `ChatPanel`, pass the active thread id: `<ChatInput threadId={firstThread?.id} />`. Add `import { useState } from "react";`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm exec vitest run src/app/ChatPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/app/ChatPanel.tsx projects/ui/src/app/ChatPanel.test.tsx
git commit -m "feat: live send in sidebar chat panel"
```

---

## Task 9: Inbox as run-thread chat (list + conversation + compose)

**Files:**
- Modify: `projects/ui/src/modules/inbox/InboxScreen.tsx`
- Modify: `projects/ui/src/modules/inbox/InboxList.tsx`
- Modify: `projects/ui/src/modules/inbox/NotificationItem.tsx`
- Modify: `projects/ui/src/modules/inbox/ConversationPane.tsx`
- Tests: the co-located `InboxScreen.test.tsx`, `InboxList.test.tsx`, `NotificationItem.test.tsx`, `ConversationPane.test.tsx`

**Interfaces:**
- Consumes: `useThreads` → `Thread[]` (`{id, agentId, workItemId, createdAt}`); `useThreadMessages`, `useSendMessage` (Task 7).
- Produces: the inbox left list renders threads (`InboxList`/`NotificationItem` take a `Thread`); `ConversationPane` takes `threadId: string` and renders that thread's messages with a live compose box; `InboxScreen` selects by thread id.

> This is one coherent change: the inbox switches its data source from `/inbox` (`InboxItem`) to `/threads` (`Thread`). The list, row, screen, and pane change together — a partial switch would not compile.

- [ ] **Step 1: Update the tests first (RED)**

Rewrite the four inbox tests to drive threads instead of inbox items. Example for `ConversationPane.test.tsx` (mock `/threads/r1/messages`):

```tsx
test("renders thread messages and sends a reply", async () => {
  renderWithClient(<ConversationPane threadId="r1" />); // helper w/ QueryClient + MSW
  expect(await screen.findByText("existing message")).toBeInTheDocument();
  await userEvent.type(screen.getByPlaceholderText("Reply to agent…"), "looks good");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  expect(await screen.findByText("looks good")).toBeInTheDocument();
});
```

For `InboxList.test.tsx` / `NotificationItem.test.tsx`: assert a thread row renders its `agentId` ("lead") and `workItemId` and calls `onSelect(thread.id)` on click. For `InboxScreen.test.tsx`: with `/threads` returning one thread, assert the pane for that thread renders; with `/threads` returning `[]`, assert the "No conversations" empty state.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/ui && pnpm exec vitest run src/modules/inbox`
Expected: FAIL (components still import `useInbox`/`InboxItem`).

- [ ] **Step 3a: `ConversationPane.tsx` — take `threadId`, live compose**

Replace the `item: InboxItem` prop with `threadId: string`; source data from `useThreadMessages(threadId)`; add a controlled reply box using `useSendMessage(threadId)`. Keep the existing bubble styling. Header shows the lead agent (static "lead" avatar/label) — drop the `StatusBadge`/`View PR`/`Approve PR` affordances (those were `InboxItem`-specific and have no backend). Minimal shape:

```tsx
import { useState } from "react";
import { Avatar } from "../../components/ui/Avatar";
import { Button } from "../../components/ui/Button";
import { useThreadMessages, useSendMessage } from "../../lib/api/hooks";
import type { Message } from "../../lib/api/hooks";

// ...keep MessageBubble + bubble style constants unchanged...

export function ConversationPane({ threadId }: { threadId: string }) {
  const { data: messages = [], isLoading } = useThreadMessages(threadId);
  const send = useSendMessage(threadId);
  const [value, setValue] = useState("");
  const disabled = value.trim().length === 0;

  function submit() {
    if (disabled) return;
    send.mutate({ content: value.trim() });
    setValue("");
  }

  return (
    <div className="flex flex-col h-full flex-1 overflow-hidden">
      <div className="flex items-center gap-2 shrink-0 px-4" style={{ height: 44, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <Avatar initials="LEAD" variant="agent" size={22} />
        <span className="text-[12.5px] font-medium text-[#c4c5cb]">lead</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isLoading && <p className="text-[11px] text-[#30333c]">Loading…</p>}
        {!isLoading && messages.length === 0 && <p className="text-[11px] text-[#30333c]">No messages yet</p>}
        {messages.map((msg: Message) => (<MessageBubble key={msg.id} message={msg} />))}
      </div>

      <div className="shrink-0 px-4 py-3" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
        <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="rounded-[6px] px-3 py-2" style={{ background: "#0e0f11", border: "1px solid rgba(255,255,255,0.09)" }}>
          <div className="flex items-center justify-between gap-2">
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Reply to agent…"
              className="bg-transparent text-[12px] flex-1 outline-none"
              style={{ color: "#c4c5cb" }}
            />
            <Button type="submit" variant="primary" disabled={disabled}>Send ↑</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

> Confirm `Button` forwards a `type` prop; if not, add `type?: "button" | "submit"` to its props and default `"button"`. If `MessageBubble`'s `agentInitials(message.agentId)` can now receive `null`, guard it: render the avatar only when `message.agentId` is set (the existing code already does `{!isUser && message.agentId && ...}`).

- [ ] **Step 3b: `NotificationItem.tsx` — render a `Thread`**

Change the prop type from `InboxItem` to `Thread`; render `item.agentId` (e.g. "lead") as the title and `item.workItemId` as the sub-label; drop `read`/`type`-badge rendering (threads have no read flag). Keep `selected` + `onSelect(item.id)` behaviour.

- [ ] **Step 3c: `InboxList.tsx` — list threads**

Replace `useInbox` with `useThreads`; drop the filter tabs and unread-count/"Mark all read" (those were inbox-item concepts). Render `Thread` rows via `NotificationItem`. Header stays "Inbox". Empty/loading states preserved.

```tsx
import { useThreads } from "../../lib/api/hooks";
import { NotificationItem } from "./NotificationItem";

export function InboxList({ selectedId, onSelect }: { selectedId?: string; onSelect: (id: string) => void }) {
  const { data: threads = [], isLoading } = useThreads();
  // header (unchanged markup, no tabs / no mark-all-read) + rows:
  //   threads.map((t) => <NotificationItem key={t.id} item={t} selected={t.id === selectedId} onSelect={onSelect} />)
}
```

- [ ] **Step 3d: `InboxScreen.tsx` — select by thread id**

```tsx
import { useNavigate, useParams } from "react-router-dom";
import { useThreads } from "../../lib/api/hooks";
import { ConversationPane } from "./ConversationPane";
import { InboxList } from "./InboxList";

export function InboxScreen() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { data: threads = [], isLoading } = useThreads();

  const selectedId = id ?? threads[0]?.id;

  if (isLoading) {
    return <div className="flex h-full items-center justify-center"><p className="text-[12px] text-[#52555e]">Loading…</p></div>;
  }
  if (threads.length === 0) {
    return <div className="flex h-full items-center justify-center"><p className="text-[12px] text-[#52555e]">No conversations</p></div>;
  }

  return (
    <div className="flex h-full overflow-hidden">
      <InboxList selectedId={selectedId} onSelect={(tid) => navigate(`/inbox/${tid}`)} />
      {selectedId && <ConversationPane threadId={selectedId} />}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm exec vitest run src/modules/inbox`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/inbox/
git commit -m "feat: inbox reads run-threads with live reply"
```

---

## Task 10: Retire the `/inbox` mock surface + move `/threads` live

**Files:**
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts`
- Modify: `projects/ui/src/lib/api/mocks/db.ts`
- Modify: `projects/ui/src/lib/api/mocks/fixtures/index.ts` (drop `inboxItems`)
- Delete: `projects/ui/src/lib/api/hooks/useInbox.ts`, `projects/ui/src/modules/inbox/useInboxConversation.ts`
- Test: `projects/ui/src/lib/api/mocks/handlers.test.ts` (or existing MSW test) — assert `/threads` honours `VITE_LIVE_API`

**Interfaces:**
- Consumes: nothing new. This removes dead code and relocates handlers.
- Produces: `/threads` + `/threads/{id}/messages` (GET/POST) live in `liveHandlers` (bypass to real `/api` when `VITE_LIVE_API` set); no `/inbox*` handlers, no `db.inboxItems`, no `useInbox`/`useInboxConversation`.

- [ ] **Step 1: Delete the dead hooks**

```bash
cd projects/ui
git rm src/lib/api/hooks/useInbox.ts src/modules/inbox/useInboxConversation.ts
```

Run: `pnpm exec tsc --noEmit` → expect NO references remain (Tasks 8–9 removed all consumers). If any remain, fix them.

- [ ] **Step 2: Remove `/inbox` handlers + move `/threads` handlers**

In `handlers.ts`: delete the four `/inbox*` handlers from `mockOnlyHandlers`. Move the three `/threads` handlers out of `mockOnlyHandlers` into the `liveHandlers` array (the pattern used for projects/work-items so they bypass to the real backend when `VITE_LIVE_API` is set). Remove the now-unused `InboxItem` import at the top of the file.

- [ ] **Step 3: Drop `inboxItems` from db + fixtures**

In `db.ts`: remove the `inboxItems` state, the `inboxItems` getter, `findInboxItem`, `markInboxRead`, `markAllInboxRead`. Keep `messages` / `messagesForThread` (still used by the mock `/threads/:id/messages`). In `fixtures/index.ts`: remove the `inboxItems` fixture export. Keep `threads` and `messages` fixtures.

- [ ] **Step 4: Update/confirm the MSW test**

Assert the live-vs-mock behaviour for `/threads`:

```ts
test("/threads is a live handler under VITE_LIVE_API", () => {
  // the exported liveHandlers array includes a handler whose path ends with /threads
  expect(liveHandlers.some((h) => String(h.info.path).endsWith("/threads"))).toBe(true);
});
```

(Adapt to the repo's existing handler-introspection helper if one exists.)

- [ ] **Step 5: Run the full UI suite + typecheck**

Run: `cd projects/ui && pnpm exec tsc --noEmit && pnpm test`
Expected: PASS, no type errors, no references to `InboxItem`/`useInbox`/`/inbox`.

- [ ] **Step 6: Commit**

```bash
git add -A projects/ui/src/lib/api/mocks projects/ui/src/lib/api/hooks projects/ui/src/modules/inbox
git commit -m "chore: retire /inbox mock; serve /threads live"
```

---

## Task 11: Final gates + docs

**Files:**
- Modify: `projects/server` + `projects/ui` (only if gates surface fixes)
- Modify: `docs/project-history.md` (add a short line for this slice)

- [ ] **Step 1: Backend gate**

Run: `cd projects/server && make coverage && make lint`
Expected: coverage ≥80%, lint clean.

- [ ] **Step 2: UI gate**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm exec tsc --noEmit`
Expected: all pass.

- [ ] **Step 3: Note the slice in project history**

Add one bullet under the current status in `docs/project-history.md`: the messaging foundation (run-threads `/threads` API + user→agent persist-only chat; inbox + sidebar share it; agent-produced chat + bus bridge deferred to A5).

- [ ] **Step 4: Commit**

```bash
git add docs/project-history.md
git commit -m "docs: record messaging foundation slice"
```

---

## Self-Review Notes (author)

- **Spec coverage:** message store (T1,T3,T4) ✓; thread=run projection (T2) ✓; `GET /threads` + `GET/POST messages` enveloped/camelCase (T5) ✓; persist-only / no bus (T5 `test_messages_do_not_touch_the_bus`) ✓; 404 owner isolation + 422 empty (T5) ✓; shared hooks (T7) ✓; inbox rewire (T9) ✓; sidebar live send (T8) ✓; `/inbox` retirement + live `/threads` (T6,T10) ✓; notifications untouched (no task changes them) ✓; attachments/agent-chat/new-message-alerts deferred (Global Constraints non-goals) ✓.
- **Type consistency:** `Message` fields (`owner_id, thread_id, role, content, agent_id`) are identical across T1/T3/T5; `ThreadView` (`id, agent_id, work_item_id, created_at`) consistent T2→T5; hook `Message` type = `components["schemas"]["Message"]` throughout T7–T9; `threadMessages` key defined once (T7) and reused.
- **Known adaptation:** `Button` may need a `type` prop (flagged in T9 Step 3a). MSW live-handler introspection in T10 Step 4 must match the repo's actual helper.
