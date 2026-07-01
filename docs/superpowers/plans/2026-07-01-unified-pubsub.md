# Unified Pub/Sub Engine + Domain Subscriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the worker's `process_next` (agent-message work-queue) and the dispatcher's `dispatch_events` (event-log fan-out) into ONE `process_subscription` engine over a `MessageSource` port, move subscription logic to `domain/messaging/`, and apply the PR #9 review (SQL only in repositories, `uow.transaction()`, Celery child tasks).

**Architecture:** A `MessageSource` port (`fetch_next`/`advance`/`on_poison`) has two impls — `BusSource` (claim/ack, serialized) and `EventLogSource` (per-subscriber cursor, fan-out). A single engine drains any subscription inside `uow.transaction()`, one item per transaction, dispatching to domain `Subscriber`s. A Celery beat task spawns one child task per subscription.

**Tech Stack:** Python 3.12 / uv / SQLAlchemy 2.0 / Celery+Beat / pytest.

## Global Constraints

- `uv`; `make coverage` (80% gate) + `make lint` (ruff+mypy) green. Backend from repo root.
- **NEW RULE (PR feedback): all SQLAlchemy/`select`/ORM queries live in `adapters/database` repositories.** Domain + interactors call repository methods, never `session.execute(select(...))`. Codified in `docs/architecture.md`.
- **`uow.transaction()`** for every consume/commit boundary — no manual `session.commit()`/`rollback()`/`close()` in interactors.
- Domain (`domain/messaging/`) is pure/transport-agnostic. The engine is one item per transaction. Sources read GLOBALLY (system); subscribers produce owner-scoped rows via the per-item owner-scoped context.
- **Behavior-preserving:** the A3 pipeline integration test (full_auto/gated_all/verify-retry) and the notification integration test (gate/finish → notifications, idempotent, isolation) must pass on the new entry points. IDs UUID-hex; immutability `model_copy`; TDD; `<type>: <description>` commits, one per task.
- Work in the `feat/event-fanout` worktree at `.worktrees/event-fanout` (PR #9 branch).

---

## File Structure

```
projects/server/src/
  domain/messaging/                # PURE: protocols + transport-agnostic subscribers only
    __init__.py
    source.py         # PoisonOutcome, Item, MessageSource protocol
    subscriber.py     # Subscriber protocol + CursorState
    context.py        # HandlerContext protocol (subscriber capabilities)
    subscribers/notifications.py   # NotificationSubscriber (pure; uses the ctx port)
  adapters/database/
    repositories.py   # + RunEventRepository.list_after; SubscriberCursorRepository (moved)
    event_log_source.py   # EventLogSource
    bus_source.py         # BusSource
  interactors/worker/              # COMPOSITION: wires domain subscribers + adapter sources
    pubsub.py         # process_subscription engine
    agent_subscriber.py   # AgentSubscriber (wraps the run dispatch) — interactor, not domain
    registry.py       # Subscription + SUBSCRIPTIONS (composition root)
    subscription_runner.py  # run_subscription(name, ...) + ctx_factory
    handlers.py       # HandlerContext concrete + dispatch (agent orchestration) — kept
    celery_app.py     # beat dispatch-subscriptions + process_subscription_task
    (delete processor.py once folded in)

> **Layering note:** `domain/messaging/` holds only the protocols (`Subscriber`, `MessageSource`, `HandlerContext`) + the pure `NotificationSubscriber` (which touches the DB only through the injected `ctx` port). The `SUBSCRIPTIONS` registry and `AgentSubscriber` (which wraps the interactor run-orchestration `dispatch`) are the **composition root** and live in `interactors/worker/` — they may import domain subscribers + adapter sources; domain must NOT import them.
  # DELETE: interactors/dispatcher/**, adapters/dispatcher/**
docs/architecture.md  # + SQL-in-repositories rule
```

---

### Task 1: SQL-in-repositories — `list_after` + `SubscriberCursorRepository` + architecture rule

**Files:**
- Modify: `adapters/database/repositories.py`, `docs/architecture.md`
- Create: (repository code in repositories.py)
- Delete (later): `adapters/dispatcher/cursor_store.py`
- Test: `tests/adapters/database/test_run_repository.py` (append), `tests/adapters/database/test_subscriber_cursor_repository.py`

**Interfaces:**
- Produces:
  - `RunEventRepository.list_after(after: int, limit: int = 100) -> list[RunEvent]` — events with `global_seq > after` (and NOT NULL), ordered by `global_seq`, limited. GLOBAL (ignores owner scoping — a system read).
  - `SubscriberCursorRepository(session)` in `repositories.py` with `get(name) -> CursorState` and `save(name, state)` (moved verbatim from `adapters/dispatcher/cursor_store.SqlSubscriberCursorStore`; `CursorState` moves to `domain/messaging/subscriber.py` in Task 3 — for now import it from its current location).

- [ ] **Step 1: Write failing tests**

Append to `tests/adapters/database/test_run_repository.py`:
```python
def test_list_after_is_global_and_ordered(session_factory):
    from adapters.database.repositories import RunEventRepository
    from adapters.database.uow import SqlUnitOfWork
    from domain.runs.events import EventType, RunEvent
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        uow.run_events.create(RunEvent(owner_id="", run_id="r2", type=EventType.LOG))
    s = session_factory()
    got = RunEventRepository(s).list_after(0, limit=10)      # no owner filter -> both runs
    assert [e.global_seq for e in got] == [1, 2]
    assert RunEventRepository(s).list_after(1, limit=10)[0].global_seq == 2
```
Create `tests/adapters/database/test_subscriber_cursor_repository.py` (move the cursor-store test here, importing `SubscriberCursorRepository` from `adapters.database.repositories` + `CursorState` from its current location).

- [ ] **Step 2: Run — fails** — `cd projects/server && uv run pytest tests/adapters/database/test_run_repository.py::test_list_after_is_global_and_ordered -v` → FAIL.

- [ ] **Step 3: Implement**

In `repositories.py`, add to `RunEventRepository`:
```python
    def list_after(self, after: int, limit: int = 100) -> list[RunEvent]:
        rows = self.session.execute(
            select(RunEventRow)
            .where(RunEventRow.global_seq.isnot(None), RunEventRow.global_seq > after)
            .order_by(RunEventRow.global_seq)
            .limit(limit)
        ).scalars().all()
        return [self._to_dto(r) for r in rows]
```
Move `SqlSubscriberCursorStore` from `adapters/dispatcher/cursor_store.py` into `repositories.py` as `SubscriberCursorRepository` (same `get`/`save` body, importing `SubscriberCursorRow`; keep importing `CursorState` from `interactors.dispatcher.subscriber` for now). Leave `adapters/dispatcher/cursor_store.py` re-exporting it for the moment (deleted in Task 7).

In `docs/architecture.md`, add under the persistence section: *"**SQL rule:** all SQLAlchemy `select`/ORM queries live in `adapters/database` repository methods. Domain and interactors depend on repository methods, never on `session.execute(select(...))` or ORM rows directly."*

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest && make lint` → PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor: move run-event read + subscriber cursor into repositories; SQL-in-repos rule"`

---

### Task 2: `MessageSource` port + `EventLogSource`

**Files:**
- Create: `domain/messaging/__init__.py` (empty), `domain/messaging/source.py`, `adapters/database/event_log_source.py`
- Test: `tests/adapters/database/test_event_log_source.py`

**Interfaces:**
- Produces:
  - `source.PoisonOutcome` (Enum: `STOP`, `CONTINUE`); `source.Item` (BaseModel: `message: Any`, `owner_id: str`, `position: int`); `source.MessageSource(Protocol)` — `fetch_next(self, uow) -> Item | None`, `advance(self, item: Item, uow) -> None`, `on_poison(self, item: Item, exc: Exception, uow_factory) -> PoisonOutcome`.
  - `event_log_source.EventLogSource(subscriber_name: str, max_retries: int = 3)` — reads the next event after this subscriber's cursor (`RunEventRepository(uow.session).list_after(cursor, limit=1)`), returns `Item(message=event, owner_id=event.owner_id, position=event.global_seq)`; `advance` saves the cursor to `item.position` (reset retries); `on_poison` opens a fresh uow, bumps the retry counter — `< max_retries` → `STOP` (cursor kept), else logs + advances cursor past `item.position` + resets → `CONTINUE`.

- [ ] **Step 1: Write failing test** — `tests/adapters/database/test_event_log_source.py`:
```python
from adapters.database.event_log_source import EventLogSource
from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent


def _sf_uow(session_factory):
    return SqlUnitOfWork(session_factory)   # system uow (no owner filter)


def test_event_log_source_fetch_advance(session_factory):
    owned = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with owned.transaction():
        owned.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.RUN_FINISHED))
    src = EventLogSource("notifications")
    uow = _sf_uow(session_factory)
    with uow.transaction():
        item = src.fetch_next(uow)
        assert item is not None and item.owner_id == "u1" and item.position == 1
        src.advance(item, uow)
    uow2 = _sf_uow(session_factory)
    with uow2.transaction():
        assert src.fetch_next(uow2) is None   # cursor advanced past the only event
```

- [ ] **Step 2: Run — fails** — → FAIL.

- [ ] **Step 3: Implement**

`domain/messaging/source.py`:
```python
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel


class PoisonOutcome(Enum):
    STOP = "stop"
    CONTINUE = "continue"


class Item(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    message: Any
    owner_id: str
    position: int


class MessageSource(Protocol):
    def fetch_next(self, uow) -> Item | None: ...
    def advance(self, item: Item, uow) -> None: ...
    def on_poison(self, item: Item, exc: Exception, uow_factory) -> PoisonOutcome: ...
```

`adapters/database/event_log_source.py`:
```python
import logging

from adapters.database.repositories import RunEventRepository, SubscriberCursorRepository
from domain.messaging.source import Item, PoisonOutcome
from interactors.dispatcher.subscriber import CursorState   # moves to domain/messaging in Task 3

logger = logging.getLogger(__name__)


class EventLogSource:
    def __init__(self, subscriber_name: str, max_retries: int = 3):
        self.subscriber_name = subscriber_name
        self.max_retries = max_retries

    def fetch_next(self, uow) -> Item | None:
        store = SubscriberCursorRepository(uow.session)
        state = store.get(self.subscriber_name)
        events = RunEventRepository(uow.session).list_after(state.last_global_seq, limit=1)
        if not events:
            return None
        e = events[0]
        return Item(message=e, owner_id=e.owner_id, position=e.global_seq)

    def advance(self, item: Item, uow) -> None:
        SubscriberCursorRepository(uow.session).save(
            self.subscriber_name, CursorState(last_global_seq=item.position, retries=0)
        )

    def on_poison(self, item, exc, uow_factory) -> PoisonOutcome:
        uow = uow_factory()
        with uow.transaction():
            store = SubscriberCursorRepository(uow.session)
            state = store.get(self.subscriber_name)
            retries = state.retries + 1
            if retries < self.max_retries:
                store.save(self.subscriber_name, CursorState(
                    last_global_seq=state.last_global_seq, retries=retries))
                return PoisonOutcome.STOP
            logger.exception("subscriber %s dead-lettering global_seq=%s after %s retries",
                             self.subscriber_name, item.position, retries)
            store.save(self.subscriber_name, CursorState(last_global_seq=item.position, retries=0))
            return PoisonOutcome.CONTINUE
```

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest tests/adapters/database/test_event_log_source.py && make lint` → PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: MessageSource port + EventLogSource"`

---

### Task 3: domain/messaging — Subscriber + context protocols + pure NotificationSubscriber

**Files:**
- Create: `domain/messaging/subscriber.py`, `domain/messaging/context.py`, `domain/messaging/subscribers/__init__.py`, `domain/messaging/subscribers/notifications.py`
- Modify: `adapters/database/event_log_source.py` (import `CursorState` from the new location)
- Test: `tests/domain/messaging/test_notification_subscriber_unit.py`

**Interfaces:**
- Produces:
  - `subscriber.CursorState` (moved from `interactors/dispatcher/subscriber.py`); `subscriber.Subscriber(Protocol)` — `name: str`, `interested_in(self, message) -> bool`, `handle(self, message, ctx) -> None`.
  - `context.HandlerContext(Protocol)` — attributes `runs`, `run_events`, `work_items`, `notifications`, `bus`, `runtime` (typed `Any`; the worker supplies a concrete object). This is the domain-side capability port; the concrete instance is the worker's `HandlerContext` dataclass.
  - `subscribers/notifications.NotificationSubscriber` (moved; PURE — `handle(event, ctx)` uses `ctx.notifications` (an owner-scoped repo supplied by the engine) for the pre-check + create; keeps the pre-check idempotency on `source_seq`; no direct `NotificationRepository` construction, no `session` param → no adapter import).

- [ ] **Step 1: Write failing test** — `tests/domain/messaging/test_notification_subscriber_unit.py` (+ `__init__.py`): assert `NotificationSubscriber().name == "notifications"`; `interested_in` on a `RunEvent(type=RUN_FINISHED)` is True, `RUN_STARTED` is False; and (with a fake `ctx` exposing a `notifications` repo double) `handle` creates a notification for a gate_requested event.

- [ ] **Step 2: Run — fails** — → FAIL.

- [ ] **Step 3: Implement** — Move `CursorState` + the `Subscriber` protocol into `domain/messaging/subscriber.py`. Add `context.HandlerContext` protocol (attrs typed `Any`). Move `NotificationSubscriber` from `interactors/dispatcher/subscribers/notifications.py` into `domain/messaging/subscribers/notifications.py`, changing `handle(event, session)` → `handle(event, ctx)` and using `ctx.notifications` for the pre-check + create (drop the in-handler `NotificationRepository(...)` construction so the subscriber has no adapter import). Update `event_log_source.py` to import `CursorState` from `domain.messaging.subscriber`. Keep `interactors/dispatcher/subscriber.py` re-exporting `CursorState` for now (deleted Task 7). NOTE: `AgentSubscriber` + the `SUBSCRIPTIONS` registry are the composition root — they are built in Task 6 (interactors/worker), NOT here, to keep domain free of interactor/adapter imports.

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest && make lint` → PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor: move subscription logic to domain/messaging"`

---

### Task 4: `BusSource`

**Files:**
- Create: `adapters/database/bus_source.py`
- Modify: (reuse the existing dead-letter logic from `interactors/worker/processor.py`)
- Test: `tests/adapters/database/test_bus_source.py`

**Interfaces:**
- Produces: `bus_source.BusSource()` — `fetch_next(uow)` = `build_message_bus(uow.session).claim_next()` → `Item(message=msg, owner_id=msg.owner_id, position=0)` (or None); `advance(item, uow)` = `build_message_bus(uow.session).ack(item.message)`; `on_poison(item, exc, uow_factory)` = fail the run + ack in a fresh transaction (the existing `_dead_letter` behavior, rewritten to use `uow.transaction()`), returns `PoisonOutcome.CONTINUE`.

- [ ] **Step 1: Write failing test** — `tests/adapters/database/test_bus_source.py`: publish a START message (via `build_message_bus`), `BusSource().fetch_next(system_uow)` returns an Item with the message + owner; `advance` acks it (a second fetch returns None). Mirror the existing `test_sql_bus`/processor coverage minimally.

- [ ] **Step 2: Run — fails** — → FAIL.

- [ ] **Step 3: Implement `bus_source.py`** — `fetch_next`/`advance` per the interface; `on_poison` = move the body of `interactors/worker/processor._dead_letter` here, converted to `uow.transaction()` (open a fresh `SqlUnitOfWork(...)` via `uow_factory`, build the bus + owner-scoped repos from `uow.session`, ack + fail the run + emit RUN_FINISHED + best-effort couple), return `PoisonOutcome.CONTINUE`.

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest tests/adapters/database/test_bus_source.py && make lint` → PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: BusSource (claim/ack + run-fail dead-letter)"`

---

### Task 5: the `process_subscription` engine

**Files:**
- Create: `interactors/worker/pubsub.py`
- Test: `tests/interactors/worker/test_pubsub.py`

**Interfaces:**
- Consumes: `MessageSource`/`Item`/`PoisonOutcome` (Task 2), `Subscriber`/`Subscription` (Task 3), the concrete `HandlerContext` (worker/handlers).
- Produces: `pubsub.process_subscription(subscription, uow_factory, ctx_factory) -> int` — drains one subscription; one item per `uow.transaction()`; dispatches to interested subscribers via a per-item owner-scoped `ctx`; on a handler exception, rolls back that item and delegates to `source.on_poison` (STOP → break, CONTINUE → count + next). `ctx_factory(uow, item) -> HandlerContext` builds the per-item owner-scoped context (repos from `uow.session` + `item.owner_id`, the bus, the runtime).

- [ ] **Step 1: Write failing tests** — `tests/interactors/worker/test_pubsub.py` with a `FakeSource` (a scripted list of items + records `advance`/`on_poison`) + fake subscribers (a recorder + a poison one):
```python
def test_engine_dispatches_and_advances(...):  # happy path: fetch->handle->advance, drained returns count
def test_engine_isolates_handler_failure_via_on_poison(...):  # handler raises -> source.on_poison called; STOP breaks, CONTINUE proceeds
```
(Use a `FakeSource` implementing `fetch_next`/`advance`/`on_poison` and a `ctx_factory` returning a simple object; assert advance called only on success, on_poison called on failure with the right outcome handling.)

- [ ] **Step 2: Run — fails** — → FAIL.

- [ ] **Step 3: Implement `pubsub.py`** (the engine from spec §4.2):
```python
def process_subscription(subscription, uow_factory, ctx_factory) -> int:
    handled = 0
    source = subscription.source
    while True:
        uow = uow_factory()
        item = None
        try:
            with uow.transaction():
                item = source.fetch_next(uow)
                if item is None:
                    return handled
                ctx = ctx_factory(uow, item)
                for sub in subscription.subscribers:
                    if sub.interested_in(item.message):
                        sub.handle(item.message, ctx)
                source.advance(item, uow)
            handled += 1
        except Exception as exc:
            if item is None:
                raise
            if source.on_poison(item, exc, uow_factory) is PoisonOutcome.STOP:
                return handled
            handled += 1
```
(`subscription.source` is built once per call from `subscription.source_factory()`.)

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest tests/interactors/worker/test_pubsub.py && make lint` → PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: unified process_subscription engine"`

---

### Task 6: composition root — AgentSubscriber, registry, subscription runner, Celery

**Files:**
- Create: `interactors/worker/agent_subscriber.py`, `interactors/worker/registry.py`, `interactors/worker/subscription_runner.py`
- Modify: `interactors/worker/celery_app.py`, `interactors/worker/handlers.py` (add `notifications` to the concrete `HandlerContext` dataclass)
- Test: `tests/interactors/worker/test_celery_subscriptions.py`

**Interfaces:**
- Produces:
  - `agent_subscriber.AgentSubscriber` — `name="agent"`, `interested_in(message) -> True`, `handle(message, ctx)` → `interactors.worker.handlers.dispatch(message, ctx)`. (Interactor layer — it wraps the run orchestration; this is why it's NOT in domain.)
  - `registry.Subscription` (dataclass: `name: str`, `source_factory: Callable[[], MessageSource]`, `subscribers: list[Subscriber]`); `registry.SUBSCRIPTIONS = [Subscription("agent-bus", BusSource, [AgentSubscriber()]), Subscription("notifications", lambda: EventLogSource("notifications"), [NotificationSubscriber()])]`. This composition root imports the domain `NotificationSubscriber`, the interactor `AgentSubscriber`, and the adapter sources — allowed here, forbidden in domain.
  - `subscription_runner.run_subscription(name, session_factory, runtime) -> int` — looks up the `Subscription` by `name`, builds its `source = source_factory()`, the `uow_factory` (`lambda: SqlUnitOfWork(session_factory)` — a system/unscoped uow), and a `ctx_factory(uow, item)` returning the concrete `HandlerContext` (owner-scoped repos from `uow.session` + `item.owner_id`, `build_message_bus(uow.session)`, `runtime`), then calls `process_subscription`.
  - `celery_app`: beat `dispatch-subscriptions` (schedule 1.0) → `dispatch_subscriptions_task` (enumerates `SUBSCRIPTIONS`, `process_subscription_task.apply_async(args=[s.name])` per subscription); `process_subscription_task(name)` → `run_subscription(name, *_deps())`. Remove the `drain-bus`/`dispatch-events` beat entries + `drain_bus`/`dispatch_events_task` tasks + the `drain` helper.

- [ ] **Step 1: Write failing test** — `test_celery_subscriptions.py`: `SUBSCRIPTIONS` names are `{"agent-bus","notifications"}`; `celery_app.conf.beat_schedule` has `dispatch-subscriptions` → `naaf.dispatch_subscriptions` and NO `drain-bus`/`dispatch-events`; `run_subscription("notifications", session_factory, FakeAgentRuntime())` on seeded gate/finish events creates the notifications (behaviour parity with the old `dispatch_events`).

- [ ] **Step 2: Run — fails** — → FAIL.

- [ ] **Step 3: Implement** — `agent_subscriber.py` + `registry.py` (composition) + `subscription_runner.py` + the concrete `HandlerContext.notifications` field + the celery changes; `process_subscription_task`/`dispatch_subscriptions_task` import `run_subscription`/`SUBSCRIPTIONS` lazily inside the task body (module stays DB/broker-free).

- [ ] **Step 4: Run — passes** — `cd projects/server && uv run pytest && make lint` → PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: Celery beat spawns a child task per subscription"`

---

### Task 7: delete old packages + rewire integration tests + full gates

**Files:**
- Delete: `interactors/dispatcher/**`, `adapters/dispatcher/**`, `interactors/worker/processor.py`
- Modify: any imports referencing the deleted modules; the pipeline + notification integration tests to drive the new entry points; `interactors/worker/handlers.py` (the concrete `HandlerContext` gains `notifications`).
- Test: existing `test_pipeline_integration.py`, `test_notification_subscriber.py`, `test_processor.py`, `test_drain.py`, `test_dispatcher.py`, `test_dispatch_task.py`

**Interfaces:** No new production interfaces — this removes the superseded code and proves parity.

- [ ] **Step 1: Rewire tests to the new entry points**
- `test_processor.py` / `test_drain.py` → drive `run_subscription("agent-bus", session_factory, runtime)` (drains the bus) instead of `process_next`/`drain`.
- `test_dispatcher.py` / `test_dispatch_task.py` → `run_subscription("notifications", ...)` (or the engine with a fake source) instead of `dispatch_events`.
- `test_pipeline_integration.py`'s `_drain` helper → loop `run_subscription("agent-bus", ...)` until it returns 0.
- `test_notification_subscriber.py` → `run_subscription("notifications", ...)`.
- Keep every ASSERTION unchanged (parity): full_auto→succeeded/done, gated_all pauses at plan then merge gate, verify retry, notifications for gate/finish + idempotency + isolation.

- [ ] **Step 2: Delete superseded modules** — `git rm -r interactors/dispatcher adapters/dispatcher; git rm interactors/worker/processor.py`. Add `notifications` to the concrete `HandlerContext` in `handlers.py` (owner-scoped `NotificationRepository`) so `ctx_factory` supplies it. Fix any remaining imports (grep for `interactors.dispatcher`, `adapters.dispatcher`, `interactors.worker.processor`, `drain`, `dispatch_events`).

- [ ] **Step 3: Run — the whole suite green** — `cd projects/server && uv run pytest -q -ra` → all pass, no failures/errors; grep confirms no references to the deleted modules remain.

- [ ] **Step 4: Full gates** — `cd projects/server && make coverage && make lint` → ≥80%, ruff+mypy clean.

- [ ] **Step 5: Manual parity sanity (document in the PR)** — the pipeline + notification integration tests passing on the new entry points IS the parity proof; note it.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "refactor: remove dispatcher/processor; drive pipeline + notifications through the unified engine"`

---

## Self-Review

**1. Spec coverage:** §4.1 MessageSource port + sources → Tasks 2/4; §4.2 engine → Task 5; §4.3 domain subscriptions → Task 3; §4.4 Celery child tasks → Task 6. §5 PR fixes: SQL-in-repos → Task 1 (+ audited as code moves), uow.transaction → the engine/sources (Tasks 2/4/5), architecture.md → Task 1. §6 migration/deletion → Task 7. §7 testing → each task + the parity integration tests (Task 7). No spec section unmapped.

**2. Placeholder scan:** No "TBD". The novel abstractions (MessageSource, Item, PoisonOutcome, EventLogSource, BusSource, process_subscription) ship as complete code with tests. Relocations (NotificationSubscriber, the dead-letter body, the cursor store) are precise move-instructions referencing the exact source — appropriate because that code already exists and was reviewed; re-transcribing it verbatim would risk drift. Task 7's test rewires name the exact assertions to preserve (parity), not "update the tests."

**3. Type consistency:** `MessageSource.fetch_next/advance/on_poison` (Task 2) is implemented by `EventLogSource` (2) + `BusSource` (4) and consumed by `process_subscription` (5). `Item(message, owner_id, position)` (2) flows through sources + engine + `ctx_factory` (6). `PoisonOutcome.STOP/CONTINUE` (2) returned by both `on_poison`s + branched in the engine (5). `Subscription(name, source_factory, subscribers)` + `SUBSCRIPTIONS` (3) consumed by `run_subscription` (6) + the parity tests (7). `Subscriber.interested_in/handle(message, ctx)` (3) implemented by `NotificationSubscriber` + `AgentSubscriber` (3), called by the engine (5). `CursorState` (moved to domain in 3) used by `EventLogSource` (2) + `SubscriberCursorRepository` (1). `run_subscription(name, session_factory, runtime)` (6) is the entry point the deleted-code tests rewire to (7). Names consistent across tasks.
