# Work-Item Thread — Phase 1 (model + API + FE unification) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-scope the conversation from *run* to *work item* — one thread per work item — and render that single thread across the Detail "Thread" tab, the inbox pane, and the sidebar chat. Humans can post; agents do not reply yet (phases 2–3).

**Architecture:** Thread id **=** work-item id (no separate Thread table). The `messages` store is reshaped to carry `kind`/`author_role`/`mentions`/`payload`; a domain mention-parser extracts `@role` tokens (stored, **not** yet dispatched). `/threads` becomes work-item-scoped. A single kind-aware React `<Thread>` component is shared by all three surfaces.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync) + Alembic, Postgres/SQLite, pytest. React + Vite + Tailwind, TanStack Query, MSW, Vitest.

## Global Constraints

- Immutability: Pydantic models updated via `model_copy(update={...})`, never mutated.
- API envelope: every response is `{success, data, error}` (+ `meta` for pagination).
- Owner scoping: every owned row carries `owner_id`; the UnitOfWork applies it as a required filter. Contract `*Out` models must never leak `owner_id`.
- IDs are UUID hex strings (32 chars). Thread id **is** the work-item id.
- TDD: write the failing test first; AAA structure; descriptive behavior names.
- Commit format: `<type>: <description>` (feat/fix/refactor/docs/test/chore).
- Gates before PR: `make coverage` (80%) and `make lint` green.
- Roles vocabulary (from `handlers._ROLE_MAP` / `domain.team.AgentRole`): `lead`, `architect`, `backend`, `frontend`, `qa`, `devops`. A human post with no `@mention` defaults to `lead`.
- Backend commands run from `projects/server`; frontend from `projects/ui`.

---

## File structure

**Backend (`projects/server/src`)**
- Modify `domain/messaging/message.py` — reshape `Message`; add `MessageKind`, `AuthorKind`.
- Create `domain/messaging/mentions.py` — `parse_mentions(text) -> list[str]`.
- Modify `domain/messaging/thread.py` — `ThreadView` + `thread_from_work_item(...)`; drop `thread_from_run`.
- Modify `adapters/database/orm.py` — `MessageRow` columns.
- Create `adapters/database/migrations/versions/0009_message_reshape.py`.
- Modify `interactors/api/contract.py` — `ThreadOut`, `ThreadDetailOut`, `MessageOut`, `MessageCreate`.
- Modify `interactors/api/routes/threads.py` — work-item-scoped routes.

**Backend tests (`projects/server/tests`)**
- Modify `tests/domain/messaging/test_message_model.py`
- Create `tests/domain/messaging/test_mentions.py`
- Modify `tests/domain/messaging/test_thread_projection.py`
- Modify `tests/adapters/database/test_message_repository.py`
- Modify `tests/api/test_threads_api.py`

**Frontend (`projects/ui/src`)**
- Modify `lib/api/schema.d.ts` — `Thread`, `ThreadDetail`, `Message` schemas.
- Modify `lib/api/queryKeys.ts` — key factories keyed by workItemId.
- Modify `lib/api/hooks/useThreads.ts`, `useThreadMessages.ts`, `useSendMessage.ts`; create `useThread.ts`; update `hooks/index.ts`.
- Modify `lib/api/mocks/db.ts`, `handlers.ts`, `fixtures/index.ts`.
- Create `components/thread/Thread.tsx`, `MessageItem.tsx`, `ThreadComposer.tsx`, `ThreadRail.tsx`, `index.ts`.
- Modify `modules/detail/TabBar.tsx`, `modules/detail/DetailScreen.tsx`.
- Modify `modules/inbox/ConversationPane.tsx`, `InboxList.tsx`, `NotificationItem.tsx`, `InboxScreen.tsx`.
- Modify `app/ChatPanel.tsx`.

**Frontend tests**
- Create `components/thread/Thread.test.tsx`.
- Modify `modules/inbox/*.test.tsx`, `app/ChatPanel.test.tsx`, `app/App.integration.test.tsx` as needed.

---

## Task 1: Reshape the `Message` domain model

**Files:**
- Modify: `projects/server/src/domain/messaging/message.py`
- Test: `projects/server/tests/domain/messaging/test_message_model.py`

**Interfaces:**
- Produces: `AuthorKind(StrEnum){USER,AGENT}`, `MessageKind(StrEnum){TEXT,FILE_WRITE,QUESTION,EVENT}`, and `Message(Entity)` with fields `owner_id, thread_id, author_kind, author_role: str|None, model_alias: str|None, kind, content, mentions: list[str], payload: dict, run_id: str|None`.

- [ ] **Step 1: Write the failing test**

Replace the file body of `tests/domain/messaging/test_message_model.py` with:

```python
from domain.messaging.message import AuthorKind, Message, MessageKind


def test_message_defaults_to_user_text():
    msg = Message(owner_id="o", thread_id="wi1", content="hello")
    assert msg.author_kind is AuthorKind.USER
    assert msg.kind is MessageKind.TEXT
    assert msg.author_role is None
    assert msg.mentions == []
    assert msg.payload == {}
    assert msg.run_id is None


def test_agent_message_carries_role_and_model():
    msg = Message(
        owner_id="o", thread_id="wi1", author_kind=AuthorKind.AGENT,
        author_role="backend", model_alias="claude-opus-4",
        kind=MessageKind.FILE_WRITE, content="wrote refresh.py",
        payload={"path": "src/auth/refresh.py", "lines": 84},
    )
    assert msg.author_role == "backend"
    assert msg.model_alias == "claude-opus-4"
    assert msg.payload["path"] == "src/auth/refresh.py"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_message_model.py -q`
Expected: FAIL (`ImportError: cannot import name 'AuthorKind'`).

- [ ] **Step 3: Write minimal implementation**

Replace `projects/server/src/domain/messaging/message.py` with:

```python
from enum import StrEnum

from pydantic import Field

from domain.base import Entity


class AuthorKind(StrEnum):
    USER = "user"
    AGENT = "agent"


class MessageKind(StrEnum):
    TEXT = "text"
    FILE_WRITE = "file_write"
    QUESTION = "question"
    EVENT = "event"


class Message(Entity):
    owner_id: str
    thread_id: str  # == work_item_id
    author_kind: AuthorKind = AuthorKind.USER
    author_role: str | None = None  # lead/backend/frontend/qa/architect/devops; None for a user
    model_alias: str | None = None
    kind: MessageKind = MessageKind.TEXT
    content: str
    mentions: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    run_id: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_message_model.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/message.py projects/server/tests/domain/messaging/test_message_model.py
git commit -m "refactor: reshape Message for work-item threads (kind/role/mentions/payload)"
```

---

## Task 2: Mention parser

**Files:**
- Create: `projects/server/src/domain/messaging/mentions.py`
- Test: `projects/server/tests/domain/messaging/test_mentions.py`

**Interfaces:**
- Produces: `TEAM_ROLES: tuple[str, ...]`, `DEFAULT_ROLE = "lead"`, `parse_mentions(text: str) -> list[str]` (deduped, ordered, only known roles), `route_targets(text: str) -> list[str]` (mentions, or `[DEFAULT_ROLE]` when none).

- [ ] **Step 1: Write the failing test**

Create `tests/domain/messaging/test_mentions.py`:

```python
from domain.messaging.mentions import DEFAULT_ROLE, parse_mentions, route_targets


def test_parses_known_roles_deduped_in_order():
    text = "@backend please sync with @qa and @backend again"
    assert parse_mentions(text) == ["backend", "qa"]


def test_ignores_unknown_and_bare_at():
    assert parse_mentions("hey @nobody and @ and plain text") == []


def test_route_targets_defaults_to_lead_when_no_mention():
    assert route_targets("no mention here") == [DEFAULT_ROLE]


def test_route_targets_uses_mentions_when_present():
    assert route_targets("@frontend take this") == ["frontend"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_mentions.py -q`
Expected: FAIL (`ModuleNotFoundError: domain.messaging.mentions`).

- [ ] **Step 3: Write minimal implementation**

Create `projects/server/src/domain/messaging/mentions.py`:

```python
import re

TEAM_ROLES: tuple[str, ...] = ("lead", "architect", "backend", "frontend", "qa", "devops")
DEFAULT_ROLE = "lead"

_MENTION_RE = re.compile(r"@([a-z]+)")


def parse_mentions(text: str) -> list[str]:
    """Return known team roles @-mentioned in ``text``, deduped, first-seen order."""
    seen: list[str] = []
    for token in _MENTION_RE.findall(text or ""):
        if token in TEAM_ROLES and token not in seen:
            seen.append(token)
    return seen


def route_targets(text: str) -> list[str]:
    """Dispatch targets: explicit mentions, else the default (lead)."""
    mentions = parse_mentions(text)
    return mentions or [DEFAULT_ROLE]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_mentions.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/mentions.py projects/server/tests/domain/messaging/test_mentions.py
git commit -m "feat: add @role mention parser for work-item threads"
```

---

## Task 3: Reshape the `ThreadView` projection (from work item)

**Files:**
- Modify: `projects/server/src/domain/messaging/thread.py`
- Test: `projects/server/tests/domain/messaging/test_thread_projection.py`

**Interfaces:**
- Consumes: `domain.work_item.WorkItem`, `domain.messaging.message.Message`.
- Produces: `ThreadView(BaseModel){id, work_item_id, title, status, participants: list[str], last_message: str|None, message_count: int, created_at}` and `thread_from_work_item(item: WorkItem, messages: list[Message]) -> ThreadView`.

- [ ] **Step 1: Write the failing test**

Replace `tests/domain/messaging/test_thread_projection.py` with:

```python
from datetime import datetime

from domain.messaging.message import AuthorKind, Message
from domain.messaging.thread import thread_from_work_item
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus


def _item() -> WorkItem:
    return WorkItem(
        id="wi1", owner_id="o", project_id="p1", kind=WorkItemKind.TASK,
        title="Implement OAuth token refresh flow", status=WorkItemStatus.IN_PROGRESS,
        created_at=datetime(2026, 7, 3, 10, 38),
    )


def test_thread_id_is_work_item_id_and_carries_title_status():
    view = thread_from_work_item(_item(), [])
    assert view.id == "wi1"
    assert view.work_item_id == "wi1"
    assert view.title == "Implement OAuth token refresh flow"
    assert view.status == "in_progress"
    assert view.message_count == 0
    assert view.last_message is None
    assert view.participants == []


def test_participants_are_distinct_senders_and_last_message_is_newest():
    msgs = [
        Message(owner_id="o", thread_id="wi1", content="assigning", author_kind=AuthorKind.AGENT, author_role="lead"),
        Message(owner_id="o", thread_id="wi1", content="on it", author_kind=AuthorKind.AGENT, author_role="backend"),
        Message(owner_id="o", thread_id="wi1", content="use option B"),  # user
    ]
    view = thread_from_work_item(_item(), msgs)
    assert view.participants == ["lead", "backend", "user"]
    assert view.last_message == "use option B"
    assert view.message_count == 3
```

Note: `WorkItemKind.TASK` must exist. If `WorkItemKind` only defines `EPIC`/`FEATURE`, check `domain/work_item.py` — the seed/board uses a task kind; use the actual member name there.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_thread_projection.py -q`
Expected: FAIL (`ImportError: cannot import name 'thread_from_work_item'`).

- [ ] **Step 3: Write minimal implementation**

Replace `projects/server/src/domain/messaging/thread.py` with:

```python
from datetime import datetime

from pydantic import BaseModel

from domain.messaging.message import Message
from domain.work_item import WorkItem


class ThreadView(BaseModel):
    id: str  # == work_item_id
    work_item_id: str
    title: str
    status: str
    participants: list[str]
    last_message: str | None
    message_count: int
    created_at: datetime | None


def _participants(messages: list[Message]) -> list[str]:
    seen: list[str] = []
    for m in messages:
        label = m.author_role if m.author_role else "user"
        if label not in seen:
            seen.append(label)
    return seen


def thread_from_work_item(item: WorkItem, messages: list[Message]) -> ThreadView:
    ordered = sorted(messages, key=lambda m: m.created_at or datetime.min)
    return ThreadView(
        id=item.id,
        work_item_id=item.id,
        title=item.title,
        status=item.status.value,
        participants=_participants(ordered),
        last_message=ordered[-1].content if ordered else None,
        message_count=len(ordered),
        created_at=item.created_at,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_thread_projection.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/thread.py projects/server/tests/domain/messaging/test_thread_projection.py
git commit -m "refactor: project ThreadView from a work item, not a run"
```

---

## Task 4: Reshape `MessageRow` ORM + migration 0009

**Files:**
- Modify: `projects/server/src/adapters/database/orm.py:133-139`
- Create: `projects/server/src/adapters/database/migrations/versions/0009_message_reshape.py`
- Test: `projects/server/tests/adapters/database/test_message_repository.py`

**Interfaces:**
- Consumes: `Message` (Task 1). `MessageRepository` is the existing generic `SqlRepository[Message]` — no code change if columns map 1:1.
- Produces: `messages` table columns `thread_id, author_kind, author_role, model_alias, kind, content, mentions (JSON), payload (JSON), run_id`.

- [ ] **Step 1: Write the failing test**

Replace `tests/adapters/database/test_message_repository.py` with:

```python
from adapters.database.uow import SqlUnitOfWork
from domain.messaging.message import AuthorKind, Message, MessageKind


def _uow(session_factory, owner="dev-user") -> SqlUnitOfWork:
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})


def test_roundtrip_preserves_kind_role_mentions_payload(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        created = uow.messages.create(Message(
            owner_id="", thread_id="wi1", author_kind=AuthorKind.AGENT,
            author_role="backend", model_alias="claude-opus-4",
            kind=MessageKind.FILE_WRITE, content="wrote it",
            mentions=["qa"], payload={"path": "src/x.py", "lines": 3},
        ))
    with uow.transaction():
        page = uow.messages.read_multi(filters={"thread_id": "wi1"}, order_by="created_at")
    got = page.results[0]
    assert got.id == created.id
    assert got.author_role == "backend"
    assert got.kind is MessageKind.FILE_WRITE
    assert got.mentions == ["qa"]
    assert got.payload == {"path": "src/x.py", "lines": 3}


def test_messages_are_owner_scoped(session_factory):
    with _uow(session_factory, "alice").transaction() as _:
        _uow(session_factory, "alice")  # noqa
    a = _uow(session_factory, "alice")
    with a.transaction():
        a.messages.create(Message(owner_id="", thread_id="wi1", content="secret"))
    b = _uow(session_factory, "bob")
    with b.transaction():
        page = b.messages.read_multi(filters={"thread_id": "wi1"})
    assert page.results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_message_repository.py -q`
Expected: FAIL (row has no `author_kind`/`kind`/`mentions`/`payload` columns).

- [ ] **Step 3: Write minimal implementation**

Replace `MessageRow` in `projects/server/src/adapters/database/orm.py` (currently lines 133-139) with:

```python
class MessageRow(_Timestamped, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_owner_thread", "owner_id", "thread_id"),)
    thread_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    author_kind: Mapped[str] = mapped_column(String(8), nullable=False, default="user")
    author_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_alias: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    content: Mapped[str] = mapped_column(String, nullable=False)
    mentions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
```

Confirm `JSON` is imported at the top of `orm.py` (the bus/run rows use it — `from sqlalchemy import JSON`). If not, add it to the existing `from sqlalchemy import ...` line.

Create `projects/server/src/adapters/database/migrations/versions/0009_message_reshape.py` (reshape — no data preserved):

```python
"""reshape messages for work-item threads

Revision ID: 0009_message_reshape
Revises: 0008_run_token_usage
Create Date: 2026-07-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_message_reshape"
down_revision = "0008_run_token_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("messages")
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("thread_id", sa.String(length=32), nullable=False, index=True),
        sa.Column("author_kind", sa.String(length=8), nullable=False),
        sa.Column("author_role", sa.String(length=32), nullable=True),
        sa.Column("model_alias", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mentions", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_messages_owner_thread", "messages", ["owner_id", "thread_id"])


def downgrade() -> None:
    op.drop_table("messages")
```

Verify the `id`/`owner_id`/timestamp column definitions against migration `0007_messages.py` and copy its exact column types/lengths for `id`, `owner_id`, `created_at`, `updated_at` so the reshaped table matches the `_Timestamped`/`Entity` base.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_message_repository.py -q`
Expected: PASS (2 passed). (Tests build the schema from ORM metadata; the migration is exercised separately by the migration test suite / `make db-upgrade`.)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/orm.py projects/server/src/adapters/database/migrations/versions/0009_message_reshape.py projects/server/tests/adapters/database/test_message_repository.py
git commit -m "feat: reshape messages table for work-item threads (migration 0009)"
```

---

## Task 5: Contract models for the new thread API

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py:236-271`
- Test: covered by Task 6 API tests.

**Interfaces:**
- Produces: `ThreadOut{id, workItemId, title, status, lastMessage, messageCount, participants, createdAt}`, `ThreadDetailOut{...ThreadOut fields..., filesWritten: list[dict]}`, `MessageOut{id, threadId, authorKind, authorRole, model, kind, content, mentions, payload, runId, createdAt}`, `MessageCreate{content, mentions?}` (mentions optional; server re-parses from content authoritatively).

- [ ] **Step 1: Write the implementation** (contract models are exercised by Task 6 tests; write them now)

Replace the "Messaging (threads)" block in `projects/server/src/interactors/api/contract.py` (currently lines 236-271) with:

```python
# ---------------------------------------------------------------------------
# Messaging (work-item threads)
# ---------------------------------------------------------------------------


class ThreadOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str  # == workItemId
    workItemId: str
    title: str
    status: str
    lastMessage: str | None = None
    messageCount: int = 0
    participants: list[str] = []
    createdAt: str


class ThreadDetailOut(ThreadOut):
    filesWritten: list[dict[str, Any]] = []


class MessageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    threadId: str
    authorKind: str
    authorRole: str | None = None
    model: str | None = None
    kind: str
    content: str
    mentions: list[str] = []
    payload: dict[str, Any] = {}
    runId: str | None = None
    createdAt: str


class MessageCreate(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v
```

- [ ] **Step 2: Commit** (compiles; behavior verified in Task 6)

```bash
git add projects/server/src/interactors/api/contract.py
git commit -m "feat: work-item thread contract models (Thread/ThreadDetail/Message)"
```

---

## Task 6: Work-item-scoped `/threads` routes

**Files:**
- Modify: `projects/server/src/interactors/api/routes/threads.py`
- Test: `projects/server/tests/api/test_threads_api.py`

**Interfaces:**
- Consumes: `thread_from_work_item` (Task 3), `parse_mentions` (Task 2), contract models (Task 5), `uow.work_items`, `uow.messages`.
- Produces: `GET /threads`, `GET /threads/{workItemId}`, `GET /threads/{workItemId}/messages`, `POST /threads/{workItemId}/messages`.

- [ ] **Step 1: Write the failing test**

Replace `tests/api/test_threads_api.py` with:

```python
from adapters.database.uow import SqlUnitOfWork
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus


def _make_item(session_factory, owner="dev-user", wid="wi1", title="OAuth refresh") -> str:
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})
    with uow.transaction():
        item = uow.work_items.create(WorkItem(
            id=wid, owner_id="", project_id="p1", kind=WorkItemKind.TASK,
            title=title, status=WorkItemStatus.IN_PROGRESS,
        ))
    return item.id


def test_list_threads_are_work_items(client, session_factory):
    wid = _make_item(session_factory)
    body = client.get("/threads").json()
    assert body["success"]
    row = next(t for t in body["data"] if t["id"] == wid)
    assert row["workItemId"] == wid
    assert row["title"] == "OAuth refresh"
    assert row["status"] == "in_progress"
    assert "owner_id" not in row


def test_post_then_list_messages_oldest_first(client, session_factory):
    wid = _make_item(session_factory)
    client.post(f"/threads/{wid}/messages", json={"content": "first"})
    client.post(f"/threads/{wid}/messages", json={"content": "second"})
    body = client.get(f"/threads/{wid}/messages").json()
    assert [m["content"] for m in body["data"]] == ["first", "second"]
    assert body["data"][0]["authorKind"] == "user"
    assert body["data"][0]["threadId"] == wid


def test_post_parses_mentions_and_defaults_author_user(client, session_factory):
    wid = _make_item(session_factory)
    res = client.post(f"/threads/{wid}/messages", json={"content": "@backend do the thing"})
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["authorKind"] == "user"
    assert data["kind"] == "text"
    assert data["mentions"] == ["backend"]


def test_empty_content_is_rejected(client, session_factory):
    wid = _make_item(session_factory)
    assert client.post(f"/threads/{wid}/messages", json={"content": "   "}).status_code == 422


def test_foreign_thread_is_404(client, session_factory):
    other = _make_item(session_factory, owner="someone-else", wid="wi9")
    assert client.get(f"/threads/{other}/messages").status_code == 404
    assert client.post(f"/threads/{other}/messages", json={"content": "x"}).status_code == 404


def test_thread_detail_returns_files_written(client, session_factory):
    wid = _make_item(session_factory)
    body = client.get(f"/threads/{wid}").json()
    assert body["success"]
    assert body["data"]["id"] == wid
    assert body["data"]["filesWritten"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py -q`
Expected: FAIL (routes still run-scoped / import errors).

- [ ] **Step 3: Write minimal implementation**

Replace `projects/server/src/interactors/api/routes/threads.py` with:

```python
from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.errors import RecordNotFound
from domain.messaging.message import AuthorKind, Message, MessageKind
from domain.messaging.mentions import parse_mentions
from domain.messaging.thread import ThreadView, thread_from_work_item
from fastapi import APIRouter, Depends, HTTPException

from interactors.api.contract import (
    MessageCreate,
    MessageOut,
    ThreadDetailOut,
    ThreadOut,
    iso,
)
from interactors.api.deps import get_uow

router = APIRouter(prefix="/threads", tags=["threads"])


def _thread_out(view: ThreadView) -> ThreadOut:
    return ThreadOut(
        id=view.id,
        workItemId=view.work_item_id,
        title=view.title,
        status=view.status,
        lastMessage=view.last_message,
        messageCount=view.message_count,
        participants=view.participants,
        createdAt=iso(view.created_at),
    )


def _message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        threadId=m.thread_id,
        authorKind=m.author_kind.value,
        authorRole=m.author_role,
        model=m.model_alias,
        kind=m.kind.value,
        content=m.content,
        mentions=m.mentions,
        payload=m.payload,
        runId=m.run_id,
        createdAt=iso(m.created_at),
    )


def _page_meta(page) -> dict:
    return {"total": page.total, "page_size": page.page_size, "page_number": page.page_number}


def _read_item_or_404(uow: SqlUnitOfWork, wid: str):
    try:
        return uow.work_items.read(wid)
    except RecordNotFound as exc:
        raise HTTPException(status_code=404, detail="thread not found") from exc


def _messages_for(uow: SqlUnitOfWork, wid: str) -> list[Message]:
    page = uow.messages.read_multi(
        filters={"thread_id": wid}, page_size=500, page_number=1, order_by="created_at"
    )
    return page.results


def _files_written(messages: list[Message]) -> list[dict]:
    return [m.payload for m in messages if m.kind is MessageKind.FILE_WRITE and m.payload.get("path")]


@router.get("", response_model=Envelope[list[ThreadOut]])
def list_threads(
    page_size: int = 50,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    page = uow.work_items.read_multi(
        page_size=page_size, page_number=page_number, order_by="-updated_at"
    )
    threads = [
        _thread_out(thread_from_work_item(item, _messages_for(uow, item.id)))
        for item in page.results
    ]
    return ok(threads, meta=_page_meta(page))


@router.get("/{id}", response_model=Envelope[ThreadDetailOut])
def get_thread(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    wid = id.hex
    item = _read_item_or_404(uow, wid)
    messages = _messages_for(uow, wid)
    base = _thread_out(thread_from_work_item(item, messages))
    detail = ThreadDetailOut(**base.model_dump(), filesWritten=_files_written(messages))
    return ok(detail)


@router.get("/{id}/messages", response_model=Envelope[list[MessageOut]])
def list_messages(
    id: UUID,
    page_size: int = 500,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    wid = id.hex
    _read_item_or_404(uow, wid)
    page = uow.messages.read_multi(
        filters={"thread_id": wid}, page_size=page_size, page_number=page_number,
        order_by="created_at",
    )
    return ok([_message_out(m) for m in page.results], meta=_page_meta(page))


@router.post("/{id}/messages", status_code=201, response_model=Envelope[MessageOut])
def post_message(
    id: UUID,
    payload: MessageCreate,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    wid = id.hex
    _read_item_or_404(uow, wid)
    created = uow.messages.create(Message(
        owner_id="",
        thread_id=wid,
        author_kind=AuthorKind.USER,
        kind=MessageKind.TEXT,
        content=payload.content,
        mentions=parse_mentions(payload.content),
    ))
    return ok(_message_out(created))
```

Note: `id: UUID` matches the existing param style (work-item ids are 32-char hex). `_read_item_or_404` replaces the old `uow.runs.read(...)`; confirm `RecordNotFound` is the exception `uow.*.read` raises (see `domain/errors.py`) and that `get_uow`/repos expose `work_items`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Run the full backend suite + lint**

Run: `cd projects/server && uv run pytest -q && make lint`
Expected: green. Fix any other test that imported `thread_from_run`/old `Message` fields (search: `grep -rn "thread_from_run\|MessageRole\|lead_agent" src tests`).

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/api/routes/threads.py projects/server/tests/api/test_threads_api.py
git commit -m "feat: work-item-scoped /threads API (list/detail/messages/post)"
```

---

## Task 7: Regenerate the FE API contract types

**Files:**
- Modify: `projects/ui/src/lib/api/schema.d.ts` (the `Thread`/`Message` schema entries + `/threads` paths)
- Modify: `projects/ui/src/lib/api/queryKeys.ts`

**Interfaces:**
- Produces: TS types `components["schemas"]["Thread"]`, `["ThreadDetail"]`, `["Message"]`; `queryKeys.threads()`, `queryKeys.thread(workItemId)`, `queryKeys.threadMessages(workItemId)`.

- [ ] **Step 1: Update the schema types**

If the repo generates `schema.d.ts` from the backend OpenAPI, prefer that generator (check `package.json` scripts for `openapi-typescript`; e.g. `pnpm gen:api`). Otherwise hand-edit. Replace the `Thread` and `Message` schema definitions in `projects/ui/src/lib/api/schema.d.ts` with:

```typescript
Thread: {
  id: string;
  workItemId: string;
  title: string;
  status: string;
  lastMessage?: string | null;
  messageCount: number;
  participants: string[];
  createdAt: string;
};
ThreadDetail: components["schemas"]["Thread"] & {
  filesWritten: Record<string, unknown>[];
};
Message: {
  id: string;
  threadId: string;
  authorKind: "user" | "agent";
  authorRole?: string | null;
  model?: string | null;
  kind: "text" | "file_write" | "question" | "event";
  content: string;
  mentions: string[];
  payload: Record<string, unknown>;
  runId?: string | null;
  createdAt: string;
};
```

- [ ] **Step 2: Update the query-key factory**

In `projects/ui/src/lib/api/queryKeys.ts`, ensure these keys exist (adapt to the file's existing object style):

```typescript
threads: () => ["threads"] as const,
thread: (workItemId?: string) => ["threads", workItemId] as const,
threadMessages: (workItemId?: string) => ["threads", workItemId, "messages"] as const,
```

- [ ] **Step 3: Type-check**

Run: `cd projects/ui && pnpm tsc --noEmit`
Expected: errors ONLY in files that consume the old `Message`/`Thread` shape (fixed in Tasks 8–12). No errors inside `schema.d.ts`/`queryKeys.ts`.

- [ ] **Step 4: Commit**

```bash
git add projects/ui/src/lib/api/schema.d.ts projects/ui/src/lib/api/queryKeys.ts
git commit -m "feat: FE contract types for work-item threads"
```

---

## Task 8: Thread hooks keyed by workItemId

**Files:**
- Modify: `projects/ui/src/lib/api/hooks/useThreads.ts`, `useThreadMessages.ts`, `useSendMessage.ts`
- Create: `projects/ui/src/lib/api/hooks/useThread.ts`
- Modify: `projects/ui/src/lib/api/hooks/index.ts`

**Interfaces:**
- Produces: `useThreads()`, `useThread(workItemId?)`, `useThreadMessages(workItemId?)`, `useSendMessage(workItemId)`; exported types `Thread`, `ThreadDetail`, `Message`.

- [ ] **Step 1: Update `useThreadMessages.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Message = components["schemas"]["Message"];

export function useThreadMessages(workItemId?: string) {
  return useQuery({
    queryKey: queryKeys.threadMessages(workItemId),
    queryFn: () => apiList<Message>(`/threads/${workItemId!}/messages`),
    enabled: Boolean(workItemId),
    select: (page) => page.results,
  });
}
```

- [ ] **Step 2: Create `useThread.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type ThreadDetail = components["schemas"]["ThreadDetail"];

export function useThread(workItemId?: string) {
  return useQuery({
    queryKey: queryKeys.thread(workItemId),
    queryFn: () => apiFetch<ThreadDetail>(`/threads/${workItemId!}`),
    enabled: Boolean(workItemId),
  });
}
```

- [ ] **Step 3: Update `useSendMessage.ts`** — change the id param name to `workItemId`, POST to `/threads/${workItemId}/messages` with body `{ content }`, and invalidate `queryKeys.threadMessages(workItemId)` + `queryKeys.thread(workItemId)` + `queryKeys.threads()` on success. Keep the existing mutation shape; only the id semantics and invalidation keys change.

- [ ] **Step 4: Update `useThreads.ts`** type export to `components["schemas"]["Thread"]` (endpoint `/threads` unchanged) and re-export `useThread`, `ThreadDetail` from `hooks/index.ts`.

- [ ] **Step 5: Type-check**

Run: `cd projects/ui && pnpm tsc --noEmit`
Expected: remaining errors only in component consumers (Tasks 9–12).

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/lib/api/hooks
git commit -m "feat: thread hooks keyed by workItemId + useThread detail hook"
```

---

## Task 9: Shared `<Thread>` component (kind-aware)

**Files:**
- Create: `projects/ui/src/components/thread/MessageItem.tsx`, `ThreadComposer.tsx`, `ThreadRail.tsx`, `Thread.tsx`, `index.ts`
- Test: `projects/ui/src/components/thread/Thread.test.tsx`

**Interfaces:**
- Consumes: `Message`, `ThreadDetail` (Task 8), `useThreadMessages`, `useSendMessage`, `useThread`.
- Produces: `<Thread workItemId={string} showRail?={boolean} compact?={boolean} header?={ReactNode} banner?={ReactNode} />` rendering messages (per `kind`), a composer, and — when `showRail` — the participants/files rail.

- [ ] **Step 1: Write the failing test**

Create `projects/ui/src/components/thread/Thread.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect } from "vitest";
import { MessageItem } from "./MessageItem";
import type { Message } from "../../lib/api/hooks";

function msg(overrides: Partial<Message>): Message {
  return {
    id: "m1", threadId: "wi1", authorKind: "agent", authorRole: "backend",
    model: null, kind: "text", content: "hello", mentions: [], payload: {},
    runId: null, createdAt: "2026-07-03T10:00:00", ...overrides,
  };
}

describe("MessageItem", () => {
  it("renders a file_write card with the path", () => {
    render(<MessageItem message={msg({ kind: "file_write", content: "wrote it", payload: { path: "src/auth/refresh.py", lines: 84 } })} />);
    expect(screen.getByText("src/auth/refresh.py")).toBeInTheDocument();
  });

  it("renders question options as buttons", () => {
    render(<MessageItem message={msg({ kind: "question", content: "which?", payload: { options: [{ id: "a", label: "Option A" }, { id: "b", label: "Option B" }] } })} />);
    expect(screen.getByRole("button", { name: /Option A/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Option B/ })).toBeInTheDocument();
  });

  it("shows the model badge for agent messages", () => {
    render(<MessageItem message={msg({ model: "claude-opus-4" })} />);
    expect(screen.getByText("claude-opus-4")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/components/thread/Thread.test.tsx`
Expected: FAIL (`Cannot find module './MessageItem'`).

- [ ] **Step 3: Write `MessageItem.tsx`**

Model the bubbles on design frame **D3** (`docs/design/NAAF Hi-Fi.dc.html` lines ~955-1024) and the existing `modules/inbox/ConversationPane.tsx` bubble styles. Create `projects/ui/src/components/thread/MessageItem.tsx`:

```tsx
import { Avatar } from "../ui/Avatar";
import type { Message } from "../../lib/api/hooks";

const AGENT_BUBBLE = "rounded-[3px_10px_10px_10px] border border-[rgba(255,255,255,0.07)] bg-[#131618] text-[#b0b2b8]";
const USER_BUBBLE = "rounded-[10px_3px_10px_10px] border border-[rgba(124,108,240,0.18)] bg-[rgba(124,108,240,0.11)] text-[#bab7f6]";

interface QuestionOption { id: string; label: string; }

function initials(m: Message): string {
  if (m.authorKind === "user") return "JW";
  const role = m.authorRole ?? "agent";
  return role.slice(0, 2).toUpperCase();
}

function FileWriteCard({ path, lines }: { path: string; lines?: number }) {
  return (
    <div className="mt-2 flex max-w-[300px] items-center gap-2 rounded-[6px] border border-[rgba(255,255,255,0.06)] bg-[#0e0f11] px-[10px] py-[7px]">
      <span className="text-[11px] font-mono text-accent flex-1 truncate">{path}</span>
      {typeof lines === "number" && <span className="text-[9.5px] text-[#42454e]">written · {lines} lines</span>}
    </div>
  );
}

function QuestionOptions({ options }: { options: QuestionOption[] }) {
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      {options.map((o) => (
        <button key={o.id} type="button" className="flex items-center gap-2 rounded-[5px] border border-[rgba(255,255,255,0.06)] bg-[#0e0f11] px-[10px] py-2 text-left text-[12px] text-[#8a8d96] hover:border-accent">
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function MessageItem({ message }: { message: Message }) {
  const isUser = message.authorKind === "user";
  const options = (message.payload?.options as QuestionOption[] | undefined) ?? [];
  const path = message.payload?.path as string | undefined;
  const lines = message.payload?.lines as number | undefined;

  return (
    <div className={`flex gap-2.5 mb-3.5 ${isUser ? "flex-row-reverse" : ""}`}>
      <Avatar initials={initials(message)} variant={isUser ? "user" : "agent"} size={26} />
      <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[600px]`}>
        <div className="mb-1 flex items-baseline gap-2">
          <span className="text-[12.5px] font-semibold text-[#c4c5cb]">
            {isUser ? "You" : (message.authorRole ?? "agent")}
          </span>
          {message.model && (
            <span className="rounded-[3px] border border-[rgba(124,108,240,0.2)] bg-[rgba(124,108,240,0.1)] px-1.5 py-px font-mono text-[9px] text-accent">
              {message.model}
            </span>
          )}
        </div>
        <div className={`px-[13px] py-2.5 text-[12.5px] leading-[1.6] ${isUser ? USER_BUBBLE : AGENT_BUBBLE}`}>
          {message.content}
          {message.kind === "question" && options.length > 0 && <QuestionOptions options={options} />}
        </div>
        {message.kind === "file_write" && path && <FileWriteCard path={path} lines={lines} />}
      </div>
    </div>
  );
}
```

If `Avatar` has no `"user"` variant, use the variant it does expose (check `components/ui/Avatar.tsx`) — keep the call valid.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm vitest run src/components/thread/Thread.test.tsx`
Expected: PASS (3 passed).

- [ ] **Step 5: Write `ThreadComposer.tsx`, `ThreadRail.tsx`, `Thread.tsx`, `index.ts`**

Create `projects/ui/src/components/thread/ThreadComposer.tsx`:

```tsx
import { useState } from "react";
import { Button } from "../ui/Button";
import { useSendMessage } from "../../lib/api/hooks";

export function ThreadComposer({ workItemId, placeholder = "Message agents… (use @ to mention)" }: { workItemId: string; placeholder?: string }) {
  const [value, setValue] = useState("");
  const send = useSendMessage(workItemId);
  const disabled = value.trim().length === 0;

  function submit() {
    if (disabled) return;
    send.mutate({ content: value.trim() });
    setValue("");
  }

  return (
    <div className="shrink-0 px-4 py-3" style={{ borderTop: "1px solid rgba(255,255,255,0.055)" }}>
      <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="rounded-[8px] border border-[rgba(255,255,255,0.09)] bg-[#101316] px-3 py-2.5">
        <input value={value} onChange={(e) => setValue(e.target.value)} placeholder={placeholder} className="mb-2 w-full bg-transparent text-[12.5px] text-[#c4c5cb] outline-none placeholder-[#22252c]" />
        <div className="flex items-center justify-end">
          <Button type="submit" variant="primary" disabled={disabled}>Send ↑</Button>
        </div>
      </form>
    </div>
  );
}
```

Create `projects/ui/src/components/thread/ThreadRail.tsx` (participants + files, from D3 lines ~1042-1069):

```tsx
import type { ThreadDetail } from "../../lib/api/hooks";

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2.5 font-mono text-[9.5px] tracking-[0.07em] text-[#28292e]">{label}</div>
      {children}
    </div>
  );
}

export function ThreadRail({ thread }: { thread?: ThreadDetail }) {
  const participants = thread?.participants ?? [];
  const files = thread?.filesWritten ?? [];
  return (
    <div className="flex w-[252px] shrink-0 flex-col gap-4 overflow-y-auto border-l border-[rgba(255,255,255,0.055)] px-3.5 py-4">
      <Section label="PARTICIPANTS">
        <div className="flex flex-col gap-2">
          {participants.map((p) => (
            <div key={p} className="flex items-center gap-2 text-[12px] text-[#c4c5cb]">{p}</div>
          ))}
        </div>
      </Section>
      <Section label="FILES WRITTEN">
        <div className="flex flex-col gap-1.5">
          {files.map((f, i) => (
            <div key={i} className="truncate rounded-[5px] border border-[rgba(255,255,255,0.06)] px-2 py-1.5 font-mono text-[10.5px] text-accent">
              {String((f as { path?: string }).path ?? "")}
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
```

Create `projects/ui/src/components/thread/Thread.tsx`:

```tsx
import type { ReactNode } from "react";
import { useThread, useThreadMessages } from "../../lib/api/hooks";
import type { Message } from "../../lib/api/hooks";
import { MessageItem } from "./MessageItem";
import { ThreadComposer } from "./ThreadComposer";
import { ThreadRail } from "./ThreadRail";

interface ThreadProps {
  workItemId: string;
  showRail?: boolean;
  header?: ReactNode;
  banner?: ReactNode;
  composerPlaceholder?: string;
}

export function Thread({ workItemId, showRail = false, header, banner, composerPlaceholder }: ThreadProps) {
  const { data: messages = [], isLoading } = useThreadMessages(workItemId);
  const { data: thread } = useThread(showRail ? workItemId : undefined);

  return (
    <div className="flex h-full flex-1 overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {header}
        {banner}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && <p className="text-[11px] text-[#30333c]">Loading…</p>}
          {!isLoading && messages.length === 0 && <p className="text-[11px] text-[#30333c]">No messages yet</p>}
          {messages.map((m: Message) => <MessageItem key={m.id} message={m} />)}
        </div>
        <ThreadComposer workItemId={workItemId} placeholder={composerPlaceholder} />
      </div>
      {showRail && <ThreadRail thread={thread} />}
    </div>
  );
}
```

Create `projects/ui/src/components/thread/index.ts`:

```typescript
export { Thread } from "./Thread";
export { MessageItem } from "./MessageItem";
export { ThreadComposer } from "./ThreadComposer";
export { ThreadRail } from "./ThreadRail";
```

- [ ] **Step 6: Type-check + test**

Run: `cd projects/ui && pnpm tsc --noEmit && pnpm vitest run src/components/thread`
Expected: no type errors in `components/thread`; tests PASS.

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/components/thread
git commit -m "feat: shared kind-aware <Thread> component"
```

---

## Task 10: Wire the Detail "Thread" tab

**Files:**
- Modify: `projects/ui/src/modules/detail/TabBar.tsx`
- Modify: `projects/ui/src/modules/detail/DetailScreen.tsx`

**Interfaces:**
- Consumes: `<Thread>` (Task 9), `useParams` itemId.
- Produces: a `Thread` tab replacing `Subagents`, rendering `<Thread workItemId={itemId} showRail />`.

- [ ] **Step 1: Rename the tab type**

In `projects/ui/src/modules/detail/TabBar.tsx`, change the `DetailTab` union member `"Subagents"` → `"Thread"` (line 3). The `Agent` pulse-dot branch is unchanged.

- [ ] **Step 2: Wire the tab in `DetailScreen.tsx`**

In `projects/ui/src/modules/detail/DetailScreen.tsx`: update `ALL_DETAIL_TABS` (line 10) to `["Spec", "Attachments", "Activity", "Agent", "Thread"]`; add the import `import { Thread } from "../../components/thread";`; replace the `Subagents` body line (line 62) with:

```tsx
{activeTab === "Thread" && <Thread workItemId={itemId ?? ""} showRail />}
```

- [ ] **Step 3: Update the Detail test**

In `projects/ui/src/modules/detail/DetailScreen.test.tsx`, replace any assertion referencing the `Subagents` tab with `Thread`. Run:

`cd projects/ui && pnpm vitest run src/modules/detail`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add projects/ui/src/modules/detail
git commit -m "feat: Detail 'Thread' tab (renamed from Subagents) rendering shared thread"
```

---

## Task 11: Inbox — thread rows + task banner over the shared thread

**Files:**
- Modify: `projects/ui/src/modules/inbox/ConversationPane.tsx`, `InboxList.tsx`, `NotificationItem.tsx`, `InboxScreen.tsx`
- Test: `projects/ui/src/modules/inbox/*.test.tsx`

**Interfaces:**
- Consumes: `useThreads`, `<Thread>`.
- Produces: `ConversationPane` = `<Thread>` + a task-link banner; `InboxScreen` selects by `workItemId`.

- [ ] **Step 1: Replace `ConversationPane.tsx` with a thin wrapper**

Model the banner on design frame **G** (`docs/design/NAAF Hi-Fi.dc.html` lines ~801-813).

```tsx
import { useThread } from "../../lib/api/hooks";
import { Thread } from "../../components/thread";

function TaskBanner({ workItemId }: { workItemId: string }) {
  const { data: thread } = useThread(workItemId);
  if (!thread) return null;
  return (
    <div className="flex items-center gap-2.5 border-b border-[rgba(255,255,255,0.05)] bg-[#0b0c0f] px-4 py-2">
      <span className="text-[11px] text-[#52555e]">Thread scoped to</span>
      <div className="flex items-center gap-1.5 rounded-[4px] border border-[rgba(255,255,255,0.07)] bg-[#131618] px-2 py-[3px]">
        <span className="font-mono text-[11px] text-accent">{thread.workItemId.slice(0, 8)}</span>
        <span className="text-[11px] text-[#52555e]">·</span>
        <span className="text-[11px] text-[#7a7d86]">{thread.title}</span>
      </div>
    </div>
  );
}

export function ConversationPane({ threadId }: { threadId: string }) {
  return (
    <Thread
      workItemId={threadId}
      banner={<TaskBanner workItemId={threadId} />}
      composerPlaceholder="Reply on this thread… (use @ to mention an agent)"
    />
  );
}
```

Keep the `threadId` prop name so `InboxScreen` needs no change to that call; it now carries a work-item id.

- [ ] **Step 2: Update `NotificationItem.tsx` / `InboxList.tsx`** to render each thread row from the new `Thread` shape — show `title`, `lastMessage`, and `participants[0]`. Replace any `thread.agentId`/`workItemId` field reads that no longer exist. Row `key`/select value is `thread.id` (= work-item id).

- [ ] **Step 3: `InboxScreen.tsx`** — no structural change; it already selects `threads[0]?.id` and passes to `ConversationPane`. Confirm `id` from `useParams` still routes (`/inbox/:id` where `id` is a work-item id).

- [ ] **Step 4: Update inbox tests**

Update `ConversationPane.test.tsx`, `InboxList.test.tsx`, `NotificationItem.test.tsx`, `InboxScreen.test.tsx` to the new `Thread`/`Message` fixture shape (mirror the `msg()`/thread factories from Task 9's test). Run:

`cd projects/ui && pnpm vitest run src/modules/inbox`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/inbox
git commit -m "feat: inbox renders shared thread with task-link banner"
```

---

## Task 12: Sidebar chat = the contextual work-item thread

**Files:**
- Modify: `projects/ui/src/app/ChatPanel.tsx`
- Test: `projects/ui/src/app/ChatPanel.test.tsx`, `projects/ui/src/app/App.integration.test.tsx`

**Interfaces:**
- Consumes: `<Thread>` (compact), `useThreads`, route params (current work item).
- Produces: sidebar showing the open work item's thread, falling back to the most recent thread.

- [ ] **Step 1: Update `ChatPanel.tsx`** — keep the collapse/expand strip; replace the messages body + input with the shared component. Derive the active work item from the route (`useParams().itemId`) and fall back to `useThreads()[0]?.id`:

```tsx
import { useParams } from "react-router-dom";
import { useThreads } from "../lib/api/hooks";
import { Thread } from "../components/thread";
import { useLocalStorage } from "../lib/hooks/useLocalStorage";
import { ChevronRightIcon } from "../components/ui";

export function ChatPanel() {
  const [open, setOpen] = useLocalStorage("naaf.chat.open", true);
  const { itemId } = useParams<{ itemId?: string }>();
  const { data: threads = [] } = useThreads();
  const workItemId = itemId ?? threads[0]?.id;

  if (!open) {
    return (
      <button aria-label="expand chat" onClick={() => setOpen(true)} className="flex h-full w-[34px] shrink-0 flex-col items-center justify-center border-l border-[rgba(255,255,255,0.055)] bg-[#080a0d] text-[#52555e]">
        <ChevronRightIcon />
      </button>
    );
  }

  return (
    <aside className="flex h-full w-[292px] shrink-0 flex-col border-l border-[rgba(255,255,255,0.055)] bg-[#09090c]">
      <div className="flex h-[44px] shrink-0 items-center justify-between border-b border-[rgba(255,255,255,0.055)] px-3">
        <span className="text-[11.5px] font-medium text-[#bab7f6]">Chat</span>
        <button aria-label="collapse" onClick={() => setOpen(false)} className="text-[#52555e]">
          <ChevronRightIcon className="rotate-180" />
        </button>
      </div>
      {workItemId
        ? <Thread workItemId={workItemId} compact composerPlaceholder="Message…" />
        : <p className="p-4 text-center text-[11.5px] text-[#52555e]">No conversations</p>}
    </aside>
  );
}
```

(`compact` is accepted by `<Thread>` as a no-rail hint; the rail is already off by default, so `compact` can be a documented no-op prop or drive tighter padding — keep the prop in `ThreadProps` if referenced.)

- [ ] **Step 2: Update `ChatPanel.test.tsx`** to the new thread fixture shape and assert it renders the first thread's messages when no route item is active. Run:

`cd projects/ui && pnpm vitest run src/app/ChatPanel.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add projects/ui/src/app/ChatPanel.tsx projects/ui/src/app/ChatPanel.test.tsx
git commit -m "feat: sidebar chat shows the contextual work-item thread"
```

---

## Task 13: Rework the MSW mock layer + integration

**Files:**
- Modify: `projects/ui/src/lib/api/mocks/db.ts`, `handlers.ts`, `fixtures/index.ts`
- Test: `projects/ui/src/lib/api/mocks/handlers.test.ts`, `projects/ui/src/app/App.integration.test.tsx`

**Interfaces:**
- Produces: MSW handlers for `GET /threads`, `GET /threads/:id`, `GET /threads/:id/messages`, `POST /threads/:id/messages` returning the new envelope shapes; seed fixtures with a couple of work-item threads incl. an `agent` message, a `file_write`, and a `question`.

- [ ] **Step 1: Update fixtures** — in `fixtures/index.ts`, replace run-thread fixtures with work-item threads: each `{ id, workItemId, title, status, lastMessage, messageCount, participants, createdAt }`, and messages of each `kind` (text/file_write/question) with `authorKind`/`authorRole`/`model`.

- [ ] **Step 2: Update `db.ts` + `handlers.ts`** — key the in-memory message store by `threadId` (= workItemId). `POST /threads/:id/messages` appends a `{ authorKind: "user", kind: "text", mentions: parsedFrom(content) }` message and returns `{ success, data }`. `GET /threads/:id` returns `ThreadDetail` with a derived `filesWritten` (payloads of `file_write` messages).

- [ ] **Step 3: Update `handlers.test.ts`** to assert the new shapes. Run:

`cd projects/ui && pnpm vitest run src/lib/api/mocks/handlers.test.ts`
Expected: PASS.

- [ ] **Step 4: Update `App.integration.test.tsx`** — fix any thread/message shape references; assert the inbox renders a thread with a `file_write` card and the Detail `Thread` tab is present. Run the full FE suite + build:

`cd projects/ui && pnpm vitest run && pnpm tsc --noEmit && pnpm build`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/api/mocks projects/ui/src/app/App.integration.test.tsx
git commit -m "test: rework MSW mocks + integration for work-item threads"
```

---

## Task 14: Docs + full verification, open PR

**Files:**
- Modify: `docs/project-history.md`

- [ ] **Step 1: Note the change** — add a short "Work-item threads (Phase 1)" paragraph to `docs/project-history.md`: threads are now work-item-scoped; the sidebar chat, inbox pane, and the Detail **Thread** tab render one shared `<Thread>`; humans post, agents don't reply yet (phases 2–3 add run narration + `@mention` dispatch). Link the spec.

- [ ] **Step 2: Full gates**

Run:
```bash
cd projects/server && make coverage && make lint
cd ../ui && pnpm vitest run && pnpm tsc --noEmit && pnpm build
```
Expected: backend ≥80% coverage + lint clean; frontend tests/type-check/build green.

- [ ] **Step 3: Commit + push + PR**

```bash
git add docs/project-history.md
git commit -m "docs: record work-item threads phase 1"
git push -u origin docs/work-item-thread-substrate
gh pr create --title "feat: work-item thread as the conversation substrate (phase 1)" \
  --body "$(cat <<'EOF'
## Summary
- Re-scopes conversations from run → work item (thread id = work-item id; no separate Thread table).
- Reshapes the `messages` store (kind/author_role/mentions/payload) + migration 0009.
- Work-item-scoped `/threads` API (list/detail/messages/post); `@role` mentions parsed + stored (not yet dispatched).
- One shared kind-aware `<Thread>` component across the Detail **Thread** tab, the inbox pane (with task-link banner), and the sidebar chat.

Humans can post; agents don't reply yet (phase 2 = run narration; phase 3 = @mention dispatch). Spec: docs/superpowers/specs/2026-07-03-work-item-thread-substrate-design.md

## Test plan
- Backend: message model / mentions / thread projection / repository / `/threads` API — `make coverage` ≥80%, `make lint` clean.
- Frontend: `<Thread>` kind rendering, Detail tab, inbox banner, sidebar contextual thread, MSW handlers, integration — `pnpm vitest run`, `pnpm tsc --noEmit`, `pnpm build`.
EOF
)"
```

---

## Self-review

**Spec coverage (Phase 1 rows only):**
- Thread = work item, no table → Tasks 3, 6. ✓
- Message reshape (kind/role/mentions/payload) → Tasks 1, 4. ✓
- Mention parsing (stored, not dispatched in P1) → Task 2, used in Task 6. ✓
- `/threads` API (list/detail/messages/post) → Task 6; contracts Task 5. ✓
- Shared `<Thread>` across Detail tab / inbox / sidebar → Tasks 9–12. ✓
- Inbox task-link banner + attention rows → Task 11. ✓
- Notifications stay separate → untouched (no task modifies notifications). ✓
- Migration as reshape-no-preserve → Task 4. ✓
- Phase 2/3 items (run narration, `@mention` dispatch, `/answer`, gates-as-questions, loop guards) → **out of scope for this plan** (separate plans). The `question` *rendering* ships now (Task 9) so phase 2 only wires data.

**Placeholder scan:** No banned placeholders; every code step carries concrete code. FE steps that adapt existing files (Tasks 8/11/13) name the exact fields to change and show the target shape.

**Type consistency:** `Message`/`AuthorKind`/`MessageKind` (Task 1) match ORM columns (Task 4), contract `MessageOut` (Task 5), route mapper (Task 6), and TS `Message` (Task 7) — field names align (`authorKind`/`authorRole`/`kind`/`mentions`/`payload`/`runId`/`model`). `thread_from_work_item` signature consistent across Tasks 3 and 6. `useThread`/`useThreadMessages`/`useSendMessage(workItemId)` consistent across Tasks 8–12.
