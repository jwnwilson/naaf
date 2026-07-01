# Event Fan-out + Notification Subscriber Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fan the durable `run_events` log out to registered server-side subscribers (decoupled from the pipeline), and ship a notification subscriber that persists owner-scoped notifications for gate/finish events.

**Architecture:** A global `global_seq` cursor is added to `run_events`; a Celery Beat `dispatch_events` task reads new events and calls each `EventSubscriber` with a per-subscriber cursor (`subscriber_cursors`), error isolation, and a retry cap. The `NotificationSubscriber` writes `Notification` rows idempotently (unique `source_seq`). Exposed via a notification API.

**Tech Stack:** Python 3.12 / uv / FastAPI / Pydantic v2 / SQLAlchemy 2.0 / Alembic / Celery+Beat / pytest.

## Global Constraints

- `uv`; `make coverage` (80% gate) + `make lint` (ruff+mypy) green. Run backend from repo root; Makefile at root.
- Hexagonal: domain pure (no I/O); adapters hold persistence; interactors wire. Immutability via `model_copy`. Envelope `{success,data,error}` (+meta). camelCase contract (read `schema.d.ts`/existing `contract.py` for style). Owner-scoping via the UoW required-filter; `owner_id` never surfaced.
- **The dispatcher + cursor store are SYSTEM components** (read `run_events` globally, like the worker claims the bus globally); the rows subscribers create stay owner-scoped (stamped from `event.owner_id`).
- **All `RunEvent`s are written by the single-dispatcher worker** (`worker_concurrency=1`), so `global_seq = MAX+1` assignment is race-free.
- Delivery is **at-least-once + idempotent** (subscribers dedupe on `global_seq`). IDs are UUID-hex. TDD; AAA; `<type>: <description>` commits, one per task.
- Work in the `feat/event-fanout` worktree at `.worktrees/event-fanout`.

---

## File Structure

```
projects/server/src/
  domain/
    runs/events.py                      # + global_seq field on RunEvent
    notifications/notification.py        # NotificationType, Notification
  adapters/
    database/
      orm.py                             # + RunEventRow.global_seq; NotificationRow; SubscriberCursorRow
      repositories.py                    # RunEventRepository.create assigns global_seq; NotificationRepository
      repository.py                      # (unchanged base)
      uow.py / ports.py                  # + notifications
      migrations/versions/0004_event_global_seq.py
      migrations/versions/0005_subscriber_cursors.py
      migrations/versions/0006_notifications.py
    dispatcher/
      cursor_store.py                    # SqlSubscriberCursorStore + CursorState
  interactors/
    dispatcher/
      subscriber.py                      # EventSubscriber protocol + CursorState import
      dispatcher.py                      # dispatch_events(session_factory, subscribers) + retry cap
      registry.py                        # SUBSCRIBERS list
      subscribers/notifications.py       # NotificationSubscriber
    worker/celery_app.py                 # + dispatch-events beat task
    api/
      contract.py                        # + NotificationOut
      routes/notifications.py            # GET /notifications, POST /notifications/{id}/read
      routes/__init__.py                 # register notifications_router
```

---

### Task 1: `global_seq` global cursor on run-events

**Files:**
- Modify: `domain/runs/events.py`, `adapters/database/orm.py`, `adapters/database/repositories.py`
- Create: `adapters/database/migrations/versions/0004_event_global_seq.py`
- Test: `projects/server/tests/adapters/database/test_run_repository.py` (append), `tests/adapters/test_migrations.py` (append)

**Interfaces:**
- Produces: `RunEvent.global_seq: int = 0`; `RunEventRow.global_seq` (Integer, unique, nullable — pre-fan-out rows stay NULL and are never dispatched); `RunEventRepository.create` assigns `global_seq = MAX(global_seq over ALL rows)+1` in addition to the per-run `seq`.

- [ ] **Step 1: Write the failing test** (append to `test_run_repository.py`)

```python
def test_run_events_get_monotonic_global_seq_across_runs(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from domain.runs.events import EventType, RunEvent
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        a = uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        b = uow.run_events.create(RunEvent(owner_id="", run_id="r2", type=EventType.LOG))
        c = uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
    assert a.global_seq == 1 and b.global_seq == 2 and c.global_seq == 3   # global, not per-run
    assert a.seq == 1 and b.seq == 1 and c.seq == 2                        # per-run unchanged
```

- [ ] **Step 2: Run — fails** — `cd projects/server && uv run pytest tests/adapters/database/test_run_repository.py::test_run_events_get_monotonic_global_seq_across_runs -v` → FAIL.

- [ ] **Step 3: Implement**

`domain/runs/events.py` — add to `RunEvent`: `global_seq: int = 0`.

`orm.py` `RunEventRow` — add (after `seq`): `global_seq: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)`.

`repositories.py` `RunEventRepository.create` — extend to also assign the global seq:
```python
    def create(self, dto: RunEvent) -> RunEvent:  # type: ignore[override]
        q = select(func.coalesce(func.max(RunEventRow.seq), 0) + 1).where(
            RunEventRow.run_id == dto.run_id
        )
        for key, value in self.required_filters.items():
            q = q.where(getattr(RunEventRow, key) == value)
        next_seq = self.session.execute(q).scalar_one()
        gq = select(func.coalesce(func.max(RunEventRow.global_seq), 0) + 1)  # global, no filters
        next_global = self.session.execute(gq).scalar_one()
        return super().create(dto.model_copy(update={"seq": next_seq, "global_seq": next_global}))
```

- [ ] **Step 4: migration + its test**

Append to `tests/adapters/test_migrations.py`:
```python
def test_migration_adds_run_events_global_seq(tmp_path):
    import os, sqlite3, subprocess
    from pathlib import Path
    db = tmp_path / "naaf.db"; server = Path(__file__).resolve().parents[2]
    env = {"naaf_db_url": f"sqlite:///{db}", "PATH": os.environ["PATH"]}
    assert subprocess.run(["uv","run","alembic","upgrade","head"], cwd=server, env=env, capture_output=True, text=True).returncode == 0
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(run_events)")}
    assert "global_seq" in cols
```
Generate `0004_event_global_seq` (`naaf_db_url="sqlite:////tmp/naaf_gen4.db" uv run alembic revision -m "event global seq" --rev-id 0004_event_global_seq` from projects/server), `down_revision="0003_runs"`, `upgrade()`: `op.add_column("run_events", sa.Column("global_seq", sa.Integer(), nullable=True)); op.create_index("ix_run_events_global_seq", "run_events", ["global_seq"], unique=True)`; `downgrade()` drops them. Rename to `0004_event_global_seq.py` if suffixed; delete the /tmp db.

- [ ] **Step 5: Run — passes** — `cd projects/server && uv run pytest && make lint` → PASS.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: global_seq cursor on run events"`

---

### Task 2: EventSubscriber protocol + SubscriberCursorStore

**Files:**
- Create: `interactors/dispatcher/__init__.py` (empty), `interactors/dispatcher/subscriber.py`, `adapters/dispatcher/__init__.py` (empty), `adapters/dispatcher/cursor_store.py`, `migrations/versions/0005_subscriber_cursors.py`
- Modify: `orm.py` (SubscriberCursorRow)
- Test: `projects/server/tests/adapters/dispatcher/test_cursor_store.py`, `tests/adapters/test_migrations.py` (append)

**Interfaces:**
- Produces:
  - `subscriber.CursorState` (BaseModel): `last_global_seq: int = 0`, `retries: int = 0`.
  - `subscriber.EventSubscriber(Protocol)`: attr `name: str`; `interested_in(self, event: RunEvent) -> bool`; `handle(self, event: RunEvent, session: Session) -> None`.
  - `orm.SubscriberCursorRow`: `name` (String PK), `last_global_seq` (Integer, default 0), `retries` (Integer, default 0), `updated_at` (DateTime). NOT owner-scoped.
  - `cursor_store.SqlSubscriberCursorStore(session)`: `get(name: str) -> CursorState` (default `CursorState()` if absent); `save(name: str, state: CursorState) -> None` (upsert).

- [ ] **Step 1: Write the failing test**

`tests/adapters/dispatcher/test_cursor_store.py` (add `tests/adapters/dispatcher/__init__.py` empty):
```python
from adapters.dispatcher.cursor_store import SqlSubscriberCursorStore
from interactors.dispatcher.subscriber import CursorState


def test_cursor_defaults_then_persists(session_factory):
    s = session_factory()
    store = SqlSubscriberCursorStore(s)
    assert store.get("notifier") == CursorState(last_global_seq=0, retries=0)
    store.save("notifier", CursorState(last_global_seq=5, retries=2)); s.commit()
    assert store.get("notifier") == CursorState(last_global_seq=5, retries=2)
    store.save("notifier", CursorState(last_global_seq=9, retries=0)); s.commit()  # upsert
    assert store.get("notifier").last_global_seq == 9
```

- [ ] **Step 2: Run — fails** — `cd projects/server && uv run pytest tests/adapters/dispatcher/test_cursor_store.py -v` → FAIL.

- [ ] **Step 3: Implement**

`interactors/dispatcher/subscriber.py`:
```python
from typing import Protocol

from domain.runs.events import RunEvent
from pydantic import BaseModel
from sqlalchemy.orm import Session


class CursorState(BaseModel):
    last_global_seq: int = 0
    retries: int = 0


class EventSubscriber(Protocol):
    name: str
    def interested_in(self, event: RunEvent) -> bool: ...
    def handle(self, event: RunEvent, session: Session) -> None: ...
```

`orm.py` — add:
```python
# system table (not owner-scoped): per-subscriber fan-out cursor
class SubscriberCursorRow(Base):
    __tablename__ = "subscriber_cursors"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_global_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
```

`adapters/dispatcher/cursor_store.py`:
```python
from adapters.database.orm import SubscriberCursorRow
from domain.base import utcnow
from interactors.dispatcher.subscriber import CursorState
from sqlalchemy.orm import Session


class SqlSubscriberCursorStore:
    def __init__(self, session: Session):
        self.session = session

    def get(self, name: str) -> CursorState:
        row = self.session.get(SubscriberCursorRow, name)
        if row is None:
            return CursorState()
        return CursorState(last_global_seq=row.last_global_seq, retries=row.retries)

    def save(self, name: str, state: CursorState) -> None:
        row = self.session.get(SubscriberCursorRow, name)
        if row is None:
            row = SubscriberCursorRow(name=name)
            self.session.add(row)
        row.last_global_seq = state.last_global_seq
        row.retries = state.retries
        row.updated_at = utcnow()
        self.session.flush()
```

- [ ] **Step 4: migration + test** — append `test_migration_adds_subscriber_cursors` (mirror Task 1's migration test, assert table `subscriber_cursors` exists). Generate `0005_subscriber_cursors` (`down_revision="0004_event_global_seq"`) creating the table (name PK String(64), last_global_seq Integer not null default 0, retries Integer not null default 0, updated_at DateTime not null).

- [ ] **Step 5: Run — passes** — `cd projects/server && uv run pytest && make lint` → PASS.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: EventSubscriber protocol + subscriber cursor store"`

---

### Task 3: `dispatch_events` dispatcher (cursor advance, isolation, retry cap)

**Files:**
- Create: `interactors/dispatcher/dispatcher.py`, `interactors/dispatcher/registry.py`
- Test: `projects/server/tests/interactors/dispatcher/test_dispatcher.py` (+ `__init__.py`)

**Interfaces:**
- Consumes: `EventSubscriber`/`CursorState` (Task 2), `SqlSubscriberCursorStore`, `RunEvent`/`RunEventRow` + `global_seq` (Task 1).
- Produces:
  - `registry.SUBSCRIBERS: list[EventSubscriber]` (starts empty; populated in Task 5).
  - `dispatcher.MAX_SUBSCRIBER_RETRIES = 3`, `dispatcher.BATCH = 100`.
  - `dispatcher.dispatch_events(session_factory, subscribers: list[EventSubscriber] | None = None) -> int` — for each subscriber, advances its cursor over new events; returns the number of (subscriber,event) pairs handled. Isolated per subscriber; a handle that keeps failing on one event retries up to `MAX_SUBSCRIBER_RETRIES` then dead-letters (logs + advances past it).

- [ ] **Step 1: Write the failing tests**

`tests/interactors/dispatcher/test_dispatcher.py`:
```python
from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent
from interactors.dispatcher.dispatcher import dispatch_events


class RecordingSub:
    name = "recorder"
    def __init__(self): self.seen = []
    def interested_in(self, event): return event.type is EventType.RUN_FINISHED
    def handle(self, event, session): self.seen.append(event.global_seq)


class PoisonSub:
    name = "poison"
    def __init__(self): self.calls = 0
    def interested_in(self, event): return True
    def handle(self, event, session): self.calls += 1; raise ValueError("boom")


def _seed_events(session_factory, n):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.RUN_FINISHED))


def test_dispatch_advances_cursor_and_filters(session_factory):
    _seed_events(session_factory, 2)
    rec = RecordingSub()
    handled = dispatch_events(session_factory, [rec])
    assert rec.seen == [2]            # only the RUN_FINISHED event (global_seq 2)
    assert handled == 2              # both events consumed (cursor advanced past both)
    # re-run: nothing new
    assert dispatch_events(session_factory, [rec]) == 0
    assert rec.seen == [2]


def test_failing_subscriber_is_isolated_and_dead_letters(session_factory):
    _seed_events(session_factory, 2)
    rec, poison = RecordingSub(), PoisonSub()
    # poison keeps failing; run dispatch enough times to exceed the retry cap
    for _ in range(5):
        dispatch_events(session_factory, [rec, poison])
    assert rec.seen == [2]                          # recorder unaffected by poison's failures
    assert poison.calls >= 3                         # retried up to the cap, then dead-lettered + advanced
```

- [ ] **Step 2: Run — fails** — `cd projects/server && uv run pytest tests/interactors/dispatcher/test_dispatcher.py -v` → FAIL.

- [ ] **Step 3: Implement `dispatcher.py`**

```python
import logging

from adapters.database.orm import RunEventRow
from adapters.dispatcher.cursor_store import SqlSubscriberCursorStore
from domain.runs.events import RunEvent
from interactors.dispatcher.subscriber import CursorState, EventSubscriber
from sqlalchemy import select

logger = logging.getLogger(__name__)

MAX_SUBSCRIBER_RETRIES = 3
BATCH = 100


def dispatch_events(session_factory, subscribers: list[EventSubscriber] | None = None) -> int:
    from interactors.dispatcher.registry import SUBSCRIBERS
    subs = SUBSCRIBERS if subscribers is None else subscribers
    return sum(_dispatch_one(session_factory, s) for s in subs)


def _dispatch_one(session_factory, sub: EventSubscriber) -> int:
    handled = 0
    while True:
        session = session_factory()
        try:
            store = SqlSubscriberCursorStore(session)
            state = store.get(sub.name)
            rows = session.execute(
                select(RunEventRow)
                .where(RunEventRow.global_seq.isnot(None), RunEventRow.global_seq > state.last_global_seq)
                .order_by(RunEventRow.global_seq)
                .limit(BATCH)
            ).scalars().all()
            if not rows:
                session.commit()
                return handled
            for row in rows:
                event = RunEvent.model_validate(row)
                if sub.interested_in(event):
                    try:
                        sub.handle(event, session)
                    except Exception:  # isolate: never let one subscriber/event break others
                        state.retries += 1
                        if state.retries < MAX_SUBSCRIBER_RETRIES:
                            store.save(sub.name, state)      # keep cursor; retry this event next tick
                            session.commit()
                            return handled
                        logger.exception(
                            "subscriber %s dead-lettering event global_seq=%s after %s retries",
                            sub.name, event.global_seq, state.retries,
                        )
                        # fall through: advance past the poison event
                state.last_global_seq = event.global_seq
                state.retries = 0
                store.save(sub.name, state)
                handled += 1
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

`registry.py`:
```python
from interactors.dispatcher.subscriber import EventSubscriber

SUBSCRIBERS: list[EventSubscriber] = []  # populated in interactors.dispatcher.subscribers
```

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest tests/interactors/dispatcher/test_dispatcher.py && make lint` → PASS. (Note: `handle` raising rolls back nothing yet because we don't call handle's writes until commit; the retry counter is persisted via `store.save`+`commit` on the early return.)

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: event dispatcher with per-subscriber cursor, isolation, retry cap"`

---

### Task 4: Notification domain + persistence

**Files:**
- Create: `domain/notifications/__init__.py` (empty), `domain/notifications/notification.py`
- Modify: `orm.py` (NotificationRow), `repositories.py` (NotificationRepository), `uow.py`, `ports.py`
- Create: `migrations/versions/0006_notifications.py`
- Test: `tests/adapters/database/test_notification_repository.py`, `tests/adapters/test_migrations.py` (append)

**Interfaces:**
- Produces: `NotificationType` (StrEnum `gate_pending/run_succeeded/run_failed/run_cancelled`); `Notification(Entity)` — `owner_id`, `run_id`, `work_item_id: str | None = None`, `type: NotificationType`, `title: str`, `body: str = ""`, `read: bool = False`, `source_seq: int`. `NotificationRow` (owner-scoped, `UNIQUE(source_seq)`); `NotificationRepository`; `uow.notifications`; `UnitOfWork.notifications`.

- [ ] **Step 1: Write the failing test**

`tests/adapters/database/test_notification_repository.py`:
```python
import pytest
from adapters.database.uow import SqlUnitOfWork
from domain.errors import IntegrityConflict
from domain.notifications.notification import Notification, NotificationType


def _uow(sf): return SqlUnitOfWork(sf, required_filters={"owner_id": "u1"})


def test_notification_round_trip(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        n = uow.notifications.create(Notification(owner_id="", run_id="r1",
            type=NotificationType.GATE_PENDING, title="Action needed", source_seq=7))
        got = uow.notifications.read(n.id)
    assert got.owner_id == "u1" and got.read is False and got.source_seq == 7


def test_source_seq_is_unique(session_factory):
    uow = _uow(session_factory)
    with pytest.raises(IntegrityConflict):
        with uow.transaction():
            uow.notifications.create(Notification(owner_id="", run_id="r1",
                type=NotificationType.RUN_SUCCEEDED, title="a", source_seq=9))
            uow.notifications.create(Notification(owner_id="", run_id="r2",
                type=NotificationType.RUN_SUCCEEDED, title="b", source_seq=9))
```

- [ ] **Step 2: Run — fails** — `cd projects/server && uv run pytest tests/adapters/database/test_notification_repository.py -v` → FAIL.

- [ ] **Step 3: Implement** — `notification.py` (the enum + `Notification(Entity)`); `orm.py` `NotificationRow(_Timestamped, Base)` `__tablename__="notifications"`, `__table_args__=(UniqueConstraint("source_seq"),)`, columns `run_id String(32) index`, `work_item_id String(32) nullable`, `type String(32)`, `title String(512)`, `body String default ""`, `read Boolean default False`, `source_seq Integer not null`; `NotificationRepository(SqlRepository[Notification])` (orm_model+dto); `uow.notifications` property (mirror `runs`); `UnitOfWork.notifications` on the protocol.

- [ ] **Step 4: migration + test** — append `test_migration_creates_notifications` (assert `notifications` table exists). Generate `0006_notifications` (`down_revision="0005_subscriber_cursors"`) creating the table with the columns above + `UniqueConstraint("source_seq")` + index on run_id.

- [ ] **Step 5: Run — passes** — `cd projects/server && uv run pytest && make lint` → PASS.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: Notification domain + repo + migration"`

---

### Task 5: NotificationSubscriber + registration + integration test

**Files:**
- Create: `interactors/dispatcher/subscribers/__init__.py`, `interactors/dispatcher/subscribers/notifications.py`
- Modify: `interactors/dispatcher/registry.py` (register it)
- Test: `tests/interactors/dispatcher/test_notification_subscriber.py`

**Interfaces:**
- Consumes: `EventSubscriber`, `dispatch_events`, `Notification`/`NotificationType`, `NotificationRepository`, `EventType`, `RunEvent`, `IntegrityConflict`.
- Produces: `NotificationSubscriber` (`name = "notifications"`); registered in `SUBSCRIBERS`.

- [ ] **Step 1: Write the failing integration test**

```python
from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent
from interactors.dispatcher.dispatcher import dispatch_events
from interactors.dispatcher.subscribers.notifications import NotificationSubscriber


def _seed(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.RUN_STARTED))
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.GATE_REQUESTED,
                                       payload={"kind": "plan"}))
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.RUN_FINISHED,
                                       payload={"status": "succeeded"}))


def _notifs(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        return uow.notifications.read_multi(page_size=0).results


def test_notifications_created_for_gate_and_finish_idempotently(session_factory):
    _seed(session_factory)
    sub = NotificationSubscriber()
    dispatch_events(session_factory, [sub])
    n = _notifs(session_factory)
    types = sorted(x.type.value for x in n)
    assert types == ["gate_pending", "run_succeeded"]     # run_started ignored
    assert all(x.owner_id == "u1" for x in n)
    # re-run the dispatcher over the same events → no duplicates
    dispatch_events(session_factory, [sub])
    assert len(_notifs(session_factory)) == 2
```

- [ ] **Step 2: Run — fails** — → FAIL.

- [ ] **Step 3: Implement `subscribers/notifications.py`**

```python
from adapters.database.repositories import NotificationRepository
from domain.errors import IntegrityConflict
from domain.notifications.notification import Notification, NotificationType
from domain.runs.events import EventType, RunEvent
from sqlalchemy.orm import Session

_FINISH_TYPE = {
    "succeeded": NotificationType.RUN_SUCCEEDED,
    "failed": NotificationType.RUN_FAILED,
    "cancelled": NotificationType.RUN_CANCELLED,
}


class NotificationSubscriber:
    name = "notifications"

    def interested_in(self, event: RunEvent) -> bool:
        return event.type in (EventType.GATE_REQUESTED, EventType.RUN_FINISHED)

    def handle(self, event: RunEvent, session: Session) -> None:
        repo = NotificationRepository(session, required_filters={"owner_id": event.owner_id})
        if event.type is EventType.GATE_REQUESTED:
            kind = event.payload.get("kind", "review")
            notif = Notification(owner_id="", run_id=event.run_id,
                                 type=NotificationType.GATE_PENDING, title="Action needed",
                                 body=f"Run {event.run_id} is awaiting {kind} approval",
                                 source_seq=event.global_seq)
        else:  # RUN_FINISHED
            status = event.payload.get("status", "succeeded")
            notif = Notification(owner_id="", run_id=event.run_id,
                                 type=_FINISH_TYPE.get(status, NotificationType.RUN_SUCCEEDED),
                                 title=f"Run {status}", body=f"Run {event.run_id} {status}",
                                 source_seq=event.global_seq)
        try:
            repo.create(notif)
            session.flush()
        except IntegrityConflict:
            session.rollback()   # already created (re-delivered event) — idempotent no-op
```

`registry.py` — set `SUBSCRIBERS = [NotificationSubscriber()]` (import it).

(NOTE: on the `IntegrityConflict` rollback, the dispatcher's `store.save`+cursor advance still runs afterward on a rolled-back session — ensure the cursor advance re-flushes cleanly. If rollback complicates the shared transaction, instead pre-check existence: `repo.read_multi(filters={"source_seq": event.global_seq})` and skip if present. Prefer the pre-check to avoid mid-transaction rollback; implement whichever keeps the dispatcher's per-batch transaction intact and the idempotency test green.)

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest && make lint` → PASS. (If the `IntegrityConflict`-rollback interferes with the batch transaction, switch the subscriber to the pre-check-existence approach noted above.)

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: notification subscriber (gate/finish -> notifications)"`

---

### Task 6: Notification API

**Files:**
- Modify: `interactors/api/contract.py`, `interactors/api/routes/__init__.py`
- Create: `interactors/api/routes/notifications.py`
- Test: `projects/server/tests/api/test_notifications_api.py`

**Interfaces:**
- Produces: `contract.NotificationOut` (camelCase: `id`, `runId`, `workItemId`, `type`, `title`, `body`, `read`, `createdAt`, `updatedAt`); `routes/notifications.py` module-level `router = APIRouter(prefix="/notifications", tags=["notifications"])` with `GET ""` (owner-scoped list, `read: bool | None` + pagination) and `POST /{id}/read`; registered in `register_routers`.

- [ ] **Step 1: Write the failing test**

```python
def test_list_and_mark_read(client, session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from domain.notifications.notification import Notification, NotificationType
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        n = uow.notifications.create(Notification(owner_id="", run_id="r1",
            type=NotificationType.GATE_PENDING, title="Action needed", source_seq=1))
    listed = client.get("/notifications").json()
    assert listed["success"] and listed["data"][0]["runId"] == "r1"
    assert listed["data"][0]["read"] is False and "owner_id" not in listed["data"][0]
    after = client.post(f"/notifications/{n.id}/read").json()["data"]
    assert after["read"] is True
    assert client.get("/notifications?read=false").json()["data"] == []
```

- [ ] **Step 2: Run — fails** — → FAIL.

- [ ] **Step 3: Implement** — add `NotificationOut` to `contract.py`; write `routes/notifications.py` (mirror `routes/projects.py` module-level style: `Depends(get_uow)`, an inline `_notification_out(n)` builder using `iso()`; `GET ""` maps `read` to a filter (`{"read": read}` when not None) + pagination meta; `POST /{id}/read` reads, `model_copy(update={"read": True})`, `uow.notifications.update`). Register `notifications_router` in `routes/__init__.py`.

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest && make coverage && make lint` → PASS, ≥80%.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: notification API (list + mark read)"`

---

### Task 7: `dispatch_events` Celery Beat task

**Files:**
- Modify: `interactors/worker/celery_app.py`
- Test: `projects/server/tests/interactors/worker/test_dispatch_task.py`

**Interfaces:**
- Consumes: `dispatch_events` (Task 3), the lazy `_deps()` session_factory (Task from A3's celery_app).
- Produces: a `naaf.dispatch_events` Celery task + a Beat entry `dispatch-events` (schedule 1.0) alongside `drain-bus`.

- [ ] **Step 1: Write the failing test**

```python
def test_celery_registers_dispatch_events_beat():
    from interactors.worker.celery_app import celery_app
    assert "dispatch-events" in celery_app.conf.beat_schedule
    assert celery_app.conf.beat_schedule["dispatch-events"]["task"] == "naaf.dispatch_events"
```

- [ ] **Step 2: Run — fails** — → FAIL.

- [ ] **Step 3: Implement** — in `celery_app.py` add to `beat_schedule`: `"dispatch-events": {"task": "naaf.dispatch_events", "schedule": 1.0}`; add the task:
```python
@celery_app.task(name="naaf.dispatch_events")
def dispatch_events_task() -> int:
    from interactors.dispatcher.dispatcher import dispatch_events
    sf, _ = _deps()
    return dispatch_events(sf)
```
(Import `dispatch_events` lazily inside the task so module import stays DB/broker-free.)

- [ ] **Step 4: Run — passes (+ full gates)** — `cd projects/server && uv run pytest && make coverage && make lint` → PASS, ≥80%, clean.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: dispatch_events Celery Beat task"`

---

## Self-Review

**1. Spec coverage:** §4.1 global cursor → Task 1. §4.2 subscriber protocol/registry → Tasks 2/3. §4.3 cursor store → Task 2. §4.4 dispatcher (cursor/isolation/retry-cap) → Task 3. §5 notification subscriber + idempotency → Tasks 4/5. §6 persistence + API → Tasks 4/6; Beat task → Task 7. §7 testing → each task's tests + the integration test (Task 5) + isolation test (Task 3). No spec section unmapped.

**2. Placeholder scan:** No "TBD". The API task (6) and migrations reference the established `routes/projects.py` / `0003_runs` patterns rather than re-transcribing boilerplate (consistent with prior plans); all load-bearing logic (global_seq assignment, `dispatch_events`, cursor store, notification subscriber) ships complete with tests. Task 5 flags a concrete either/or (IntegrityConflict-rollback vs pre-check) with a clear decision rule (keep the batch transaction intact + idempotency test green).

**3. Type consistency:** `RunEvent.global_seq` (Task 1) is read by the dispatcher (Task 3) + subscriber (Task 5). `CursorState`/`EventSubscriber` (Task 2) are consumed by `dispatch_events` (Task 3) + `NotificationSubscriber` (Task 5). `SqlSubscriberCursorStore.get/save` (Task 2) used in Task 3. `dispatch_events(session_factory, subscribers=None) -> int` (Task 3) called by tests (5) + the Beat task (7). `Notification`/`NotificationType`/`NotificationRepository` (Task 4) consumed by the subscriber (5) + API (6). `NotificationOut` camelCase (6) matches the contract style. `SUBSCRIBERS` (Task 3 registry) populated in Task 5. Names consistent throughout.
