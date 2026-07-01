# Unified Pub/Sub Engine + Domain Subscriptions — Design

**Date:** 2026-07-01
**Status:** Approved design, pending implementation plan
**Branch:** `feat/event-fanout` (PR #9) — this implements the PR feedback + the requested refactor on the same branch, BEFORE merge.
**Builds on / refactors:** the A3 agent-message bus (`interactors/worker/processor.py`) and the event fan-out dispatcher (`interactors/dispatcher/`).

## 1. Problem & goal

The worker's `process_next` (agent-message work-queue) and the dispatcher's `dispatch_events` (event-log fan-out) contain near-duplicate "consume → dispatch with isolation + retry + dead-letter → advance → commit" loops, with manual session management and (in the dispatcher) raw SQLAlchemy in an interactor. This unifies them into **one pub/sub engine** over a `MessageSource` port, moves the **subscription logic to `domain/`** (transport-agnostic), and applies the PR #9 review: **all SQL in `adapters/database` repositories**, **`uow.transaction()` instead of manual session management**, and **Celery child tasks per subscription** for parallelism + robustness.

### Success criterion

> One `process_subscription` engine drives BOTH the agent-message flow and the event-log fan-out via a `MessageSource` port; subscription definitions live in `domain/messaging/`; no `select(...)`/raw SQLAlchemy exists outside `adapters/database` (enforced by a rule in `architecture.md`); every consume loop uses `uow.transaction()`; a Celery beat task spawns one child task per subscription (fan-out subscribers run in parallel, the agent bus stays serialized). All existing pipeline + notification + API tests stay green (behavior preserved). `make coverage` (80%) + `make lint` green.

## 2. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Unification depth | **One engine + `MessageSource` port** | Literally "a single pub/sub function"; the work-queue vs cursor semantics live behind the port |
| Subscription location | **`domain/messaging/`** | Which subscriber reacts to what is business logic, transport-agnostic |
| Transaction | **`uow.transaction()`, one item per transaction** | PR feedback; preserves the per-event atomicity the dispatcher needs |
| SQL location | **only `adapters/database` repositories** | PR feedback; codified in `architecture.md` |
| Parallelism | **Celery child task per subscription** (`apply_async`) | PR feedback; fan-out subscribers parallelize; agent bus stays serialized |

## 3. Scope

**In:** the `MessageSource` port + `BusSource`/`EventLogSource` impls; the `Subscriber` protocol + subscription registry in `domain/messaging/`; the single `process_subscription` engine in `interactors/worker/`; moving the dispatcher's raw SQL into repositories + the cursor store into an `adapters/database` repository; converting both loops to `uow.transaction()`; the Celery beat task + per-subscription child tasks (replacing `drain_bus`/`dispatch_events`); the `architecture.md` SQL rule; deleting the now-empty `interactors/dispatcher/` package.

**Out:** new subscribers (viz/broadcast — the design just makes adding them trivial); the UI inbox wiring; hardening `claim_next` for multi-worker concurrency (the agent-bus child task stays serialized; `worker_concurrency=1` assumption preserved — a documented limitation). No behavior change to the pipeline or notifications — this is a structural refactor.

## 4. Architecture

### 4.1 `MessageSource` port (`domain/messaging/source.py` protocol; impls in `adapters/database/`)
A source encapsulates a subscription's delivery semantics against a session-bearing `uow`:
- `fetch_next(uow) -> Item | None` — the next unprocessed item (or `None` when drained).
- `advance(item, uow) -> None` — mark consumed within the same transaction.
- `on_poison(item, exc, uow_factory) -> PoisonOutcome` — dead-letter policy in its OWN fresh transaction; returns whether to keep draining (`CONTINUE`) or stop this tick (`STOP`, e.g. below the retry cap).

`Item` is a small union/wrapper carrying the domain object (`AgentMessage` or `RunEvent`) + its `owner_id` + its position. Impls:
- **`BusSource`** (`adapters/database/bus_source.py` or reuse `adapters/bus/`): `fetch_next` = `claim_next`; `advance` = `ack`; `on_poison` = fail the run + ack (existing dead-letter), `CONTINUE`. Serialized (one message at a time).
- **`EventLogSource`** (`adapters/database/event_log_source.py`): constructed with a `subscriber_name`; `fetch_next` = next `run_event` after this subscriber's cursor (via `RunEventRepository.list_after`); `advance` = save cursor to the item's `global_seq`; `on_poison` = bump retry counter, `STOP` below the cap, else advance-past + `CONTINUE`.

### 4.2 The engine (`interactors/worker/pubsub.py`)
```python
def process_subscription(subscription, uow_factory) -> int:
    handled = 0
    while True:
        uow = uow_factory()
        item = None
        try:
            with uow.transaction():
                item = subscription.source.fetch_next(uow)
                if item is None:
                    break
                ctx = _handler_context(uow, item)      # owner-scoped repos + publish, from uow.session
                for sub in subscription.subscribers:
                    if sub.interested_in(item.message):
                        sub.handle(item.message, ctx)
                subscription.source.advance(item, uow)
            handled += 1
        except Exception as exc:
            if item is None:
                raise                                   # infra error (fetch/commit): let the task retry
            outcome = subscription.source.on_poison(item, exc, uow_factory)
            if outcome is PoisonOutcome.STOP:
                break
            handled += 1
    return handled
```
One item per `uow.transaction()`; on a handler exception the transaction rolls back that item's writes (earlier items already committed), then the source's poison policy runs in its own transaction. Both subscriptions use this ONE function.

### 4.3 Subscriptions (`domain/messaging/`)
- `Subscriber` protocol (`subscriber.py`): `name: str`, `interested_in(message) -> bool`, `handle(message, ctx) -> None`. `ctx` is a `HandlerContext` port (owner-scoped repos + publish) — domain declares the interface; the worker supplies the impl.
- `AgentSubscriber` wraps the existing lead/engineer/qa `dispatch` (moved here or referenced) — `interested_in` = always; `handle` = route by role.
- `NotificationSubscriber` moves here from `interactors/dispatcher/subscribers/`.
- `registry.py`: `SUBSCRIPTIONS` — a list of `Subscription(name, source_factory, subscribers)`; `agent-bus` (BusSource + AgentSubscriber) and `notifications` (EventLogSource + NotificationSubscriber). Adding a subscriber = add a `Subscription`.

### 4.4 Celery (`interactors/worker/celery_app.py`)
- A beat task `dispatch_subscriptions` (every ~1s) enumerates `SUBSCRIPTIONS` and `process_subscription_task.apply_async(args=[name])` — one child task per subscription. Replaces `drain_bus` + `dispatch_events`.
- `process_subscription_task(name)` looks up the subscription by name, builds its source from the lazy `_deps()` session_factory, and runs `process_subscription`.
- Event-log subscriptions run in parallel child tasks (independent cursors). `agent-bus` is one child task; because `worker_concurrency=1` the tasks serialize in the worker regardless, preserving one-in-flight-per-recipient — the child-task split is for future horizontal scaling of the fan-out subscribers.

## 5. PR feedback — applied consistently

- **SQL only in `adapters/database` repositories.** Move the dispatcher's `select(RunEventRow)…` into `RunEventRepository.list_after(after: int, limit: int) -> list[RunEvent]`; move `SqlSubscriberCursorStore` into `adapters/database/` as a repository (`SubscriberCursorRepository`). Audit the PR's new code for any other raw SQLAlchemy outside repositories. `docs/architecture.md`: add a rule — *"All SQLAlchemy/SQL lives in `adapters/database` repositories. Domain and interactors depend on repository methods, never on `select`/ORM queries."*
- **`uow.transaction()`** replaces manual `session_factory()`/`commit()`/`rollback()`/`close()` in the engine and the dead-letter paths.
- **Celery child tasks** as in §4.4.

## 6. Migration of existing code
- `interactors/worker/processor.py` → folded into the engine + `BusSource`. Delete once `process_subscription` covers it.
- `interactors/dispatcher/` (dispatcher.py, subscriber.py, registry.py, subscribers/) → moved: subscriber protocol + subscribers + registry to `domain/messaging/`; the loop into the engine; **delete the package**.
- `adapters/dispatcher/cursor_store.py` → `adapters/database/` repository. Delete the `adapters/dispatcher/` package.

## 7. Testing
- **Engine unit tests** (fake `MessageSource` + fake subscribers): fetch→dispatch→advance happy path; a handler exception rolls back only that item (earlier committed) and invokes `on_poison`; `STOP` vs `CONTINUE`; drained (`fetch_next` None) returns; infra error (fetch raising) propagates.
- **Source adapter tests:** `BusSource` (claim/ack/fail-run poison — mirror the old processor tests); `EventLogSource` (cursor read via `RunEventRepository.list_after`, advance, retry-cap dead-letter — mirror the old dispatcher tests).
- **Behavior-preserving:** the existing full pipeline integration test (full_auto/gated_all/verify-retry) and the notification integration test (gate/finish → notifications, idempotent, isolation) must pass unchanged (adapting only the entry point `process_next`→`process_subscription("agent-bus", …)` / `dispatch_events`→`process_subscription("notifications", …)`).
- **Celery:** beat has `dispatch-subscriptions`; child task registered; import stays DB/broker-free.
- 80% coverage + ruff/mypy clean.

## 8. Conventions (carried)
Hexagonal (SQL in repositories only — newly codified); domain pure; `uow.transaction()` boundaries; envelope; owner-scoping (sources read globally as system processes, subscribers produce owner-scoped rows via `uow.session`); immutability; TDD; `<type>: <description>` commits. Local-First.

## 9. Implementation phasing (for the plan)
1. `architecture.md` SQL rule + `RunEventRepository.list_after` + move `SubscriberCursorStore` → `adapters/database` repository (SQL-in-repos; tests).
2. `MessageSource` port + `PoisonOutcome`/`Item` + `EventLogSource` (fetch/advance/on_poison) over the repos.
3. `BusSource` (wraps claim/ack + the run-fail dead-letter).
4. `domain/messaging/`: `Subscriber` protocol + `HandlerContext` port + move `NotificationSubscriber` + wrap agent `dispatch` as `AgentSubscriber` + the `SUBSCRIPTIONS` registry.
5. The `process_subscription` engine (`uow.transaction`, per-item, isolation via `on_poison`) + engine unit tests.
6. Rewire Celery: beat `dispatch-subscriptions` + `process_subscription_task` (child per subscription); delete `drain_bus`/`dispatch_events`.
7. Delete `interactors/dispatcher/` + `adapters/dispatcher/`; update `process_next`→engine call sites; make the pipeline + notification integration tests pass on the new entry points; full gates.
