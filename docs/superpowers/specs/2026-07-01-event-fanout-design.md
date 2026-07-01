# Event Fan-out + Notification Subscriber — Design

**Date:** 2026-07-01
**Status:** Approved design, pending implementation plan
**Builds on:** A3 run pipeline (`run_events` durable log, the Celery worker) — merged to `main`.
**Relates to:** the foundation for **A5e (notification system)**.

## 1. Problem & goal

The A3 pipeline emits `RunEvent`s (durable, append-only, per-run ordered) that the UI consumes read-side via SSE. But there is no way to **hook server-side functionality onto those events** — e.g. create a notification when a gate needs attention, or drive a live visualization. This build adds a **fan-out substrate**: registered subscribers react to the run-event log, decoupled from the pipeline (they cannot slow or break a run), plus a first concrete subscriber that **persists notifications** (seeding the inbox / A5e).

### Success criterion

> With the worker running, completing (or gating) a run causes a background **dispatcher** to fan the resulting `RunEvent`s out to subscribers; the shipped **notification subscriber** creates owner-scoped `Notification` rows for `gate_requested` and `run_finished` events, idempotently (re-running the dispatcher creates no duplicates), observable via `GET /notifications`; a deliberately-failing subscriber is isolated and does not block others or the pipeline. `make coverage` (80%) + `make lint` green.

## 2. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Fan-out mechanism | **Event-log dispatcher over `run_events`** | The durable ordered log already exists; subscribers consume it decoupled + resumably and can't affect run correctness |
| Deliverable scope | **Substrate + a notification subscriber** (persist notifications) | Proves the seam end-to-end and seeds the inbox / A5e |
| Delivery | **At-least-once + idempotent** (per-subscriber cursor advances after success) | Simple, durable; subscribers dedupe on the event's `global_seq` |
| Global ordering | **`global_seq` on `run_events`** (`MAX+1` in the repo) | The dispatcher needs a stable global cursor; safe because all events are written by the single-dispatcher worker |

## 3. Scope

**In:** a `global_seq` global cursor on run-events; an `EventSubscriber` protocol + a module-level registry; a `SubscriberCursorStore` (per-subscriber cursor); a `dispatch_events` function run as a Celery Beat task; a `Notification` domain/persistence/repo + migration; a `NotificationSubscriber`; a notification API (`GET /notifications`, mark-read); tests.

**Out:** viz/broadcast subscribers (a future subscriber — same pattern, not built here); wiring the UI **inbox** screen to `/notifications` (follow-up, per the A3 UI-divergence pattern — the API is live, the UI wiring is separate); real-time WebSocket/Redis broadcast; email/push delivery channels (A5e proper). Multi-worker concurrency hardening (the dispatcher, like the drain, relies on `worker_concurrency=1`).

## 4. Architecture — the fan-out substrate

The pipeline is unchanged; fan-out is a **new consumer** of the `run_events` log.

### 4.1 Global event cursor
`RunEvent.seq` is per-run. Add `global_seq: int` to `run_events`, assigned by `RunEventRepository.create` as `MAX(global_seq)+1` across all rows (mirrors the existing per-run `seq` assignment). This is safe because **every** `RunEvent` is written by the worker, which runs single-dispatcher (`worker_concurrency=1`). The dispatcher reads `run_events WHERE global_seq > cursor ORDER BY global_seq`.

### 4.2 Subscriber registry
A module-level list of subscribers. Interface (`interactors/dispatcher/subscriber.py`):
```python
class EventSubscriber(Protocol):
    name: str                                    # unique — the cursor key
    def interested_in(self, event: RunEvent) -> bool: ...
    def handle(self, event: RunEvent, session: Session) -> None: ...
```
`handle` receives the DB session; a subscriber builds whatever **owner-scoped** repo it needs from `event.owner_id` (the dispatcher reads events globally as a system process — like the worker claims the bus globally — but the rows subscribers produce stay owner-scoped). Registration is a static list (`SUBSCRIBERS = [NotificationSubscriber()]`); dynamic/DB registration is future.

### 4.3 SubscriberCursorStore
A system table `subscriber_cursors` (`name` PK, `last_global_seq`, `updated_at`) — **not** owner-scoped. A small adapter (`adapters/dispatcher/cursor_store.py`) with `get(name) -> int` (default 0) and `set(name, seq)`, session-based (participates in the dispatcher's transaction).

### 4.4 Dispatcher
`dispatch_events(session_factory) -> int` (testable plain function; returns events dispatched). For each subscriber, in its own session/transaction:
- read its cursor;
- fetch the next batch of events after it (`global_seq > cursor ORDER BY global_seq LIMIT batch`, global read);
- for each event the subscriber `interested_in`: call `handle(event, session)`; on success, set the cursor to that event's `global_seq`; commit per event (or per small batch) so progress is durable.
- **Error isolation + retry cap:** wrap each `handle`; a subscriber that keeps failing on one event retries up to `MAX_SUBSCRIBER_RETRIES`, then the dispatcher logs it and advances the cursor past it (per-subscriber dead-letter) so one poison event can't stall a subscriber forever. A failure in one subscriber never affects another (separate cursors/transactions) or the pipeline.

Runs as a **Celery Beat task** (`dispatch_events` every ~1s) alongside `drain_bus`, in the same `worker_concurrency=1` worker; import-safe (lazy deps like `drain_bus`).

## 5. The notification subscriber

### 5.1 Domain (`domain/notifications/`)
- `NotificationType` (StrEnum): `gate_pending · run_succeeded · run_failed · run_cancelled`.
- `Notification(Entity)`: `owner_id`, `run_id`, `work_item_id: str | None`, `type: NotificationType`, `title: str`, `body: str`, `read: bool = False`, `source_seq: int` (the event's `global_seq`, the idempotency key).

### 5.2 Subscriber (`interactors/dispatcher/subscribers/notifications.py`)
- `interested_in`: `event.type in {GATE_REQUESTED, RUN_FINISHED}`.
- `handle(event, session)`: build `NotificationRepository(session, required_filters={"owner_id": event.owner_id})`; map the event to a notification:
  - `gate_requested` → `type=gate_pending`, `title="Action needed"`, `body="Run {run_id} is awaiting {kind} approval"` (kind from `event.payload["kind"]`).
  - `run_finished` → read `event.payload["status"]` → `run_succeeded`/`run_failed`/`run_cancelled`, with a matching title/body.
  - set `source_seq = event.global_seq`, `run_id = event.run_id`.
  - create it; a duplicate (re-delivered event) is caught via the unique key and treated as a no-op (idempotent).

### 5.3 Idempotency
`notifications` has `UNIQUE(source_seq)` (`global_seq` is globally unique; one event yields at most one notification). The dispatcher does `handle` + cursor-advance in **one transaction**, so at-least-once delivery + the unique key = an exactly-once effect. The subscriber catches `IntegrityConflict` on the create and returns (already handled).

## 6. Persistence & API

- `NotificationRow` ORM (owner-scoped via `_Timestamped`; `UNIQUE(source_seq)`); `NotificationRepository`; UoW `notifications` property + `UnitOfWork` protocol entry.
- `run_events.global_seq` column; `subscriber_cursors` table.
- One Alembic migration (`global_seq` + `notifications` + `subscriber_cursors`).
- API (`interactors/api/routes/notifications.py`, module-level router, camelCase contract, envelope, owner-scoped):
  - `GET /notifications?read=<bool>&page_size=&page_number=` → `NotificationOut[]` (list, filterable by read).
  - `POST /notifications/{id}/read` → mark read → `NotificationOut`.
  - `NotificationOut` (camelCase): `id`, `runId`, `workItemId`, `type`, `title`, `body`, `read`, `createdAt`, `updatedAt`.

## 7. Testing

- **Unit:** `dispatch_events` — cursor advances only past handled events; a failing subscriber is isolated (others advance) and hits the retry cap → dead-letters past a poison event; `global_seq` assignment is monotonic across runs.
- **Adapter:** `NotificationRepository` (round-trip, owner-scoped, `UNIQUE(source_seq)` conflict), `SubscriberCursorStore` (get default 0 / set / persist), migration creates the columns/tables.
- **Integration (key):** seed a run + its events (or run the pipeline via the worker), call `dispatch_events(session_factory)` → notifications exist for `gate_requested` + `run_finished` with the right types/owner; **re-run** → no duplicates (idempotent); register a deliberately-failing fake subscriber alongside the real one → it's isolated (the notification subscriber still advances).
- **API:** `GET /notifications` (owner-scoped, `read` filter, camelCase), mark-read flips `read`, cross-owner 404/empty.
- 80% coverage + ruff/mypy clean. The dispatcher Celery task is import-safe + tested via the plain `dispatch_events` function (no Redis needed).

## 8. Conventions (carried)
Envelope `{success,data,error}` (+`meta`); camelCase contract; immutability (`model_copy`); owner-scoping (subscribers stamp `owner_id` from the event); UUID-hex ids; TDD; `<type>: <description>` commits. Local-First (no Temporal). The dispatcher, like the worker, is a system process reading the log globally but producing owner-scoped rows.

## 9. Implementation phasing (for the plan)
1. `global_seq` on `run_events` (ORM + `RunEventRepository.create` assigns it + migration) + tests.
2. `EventSubscriber` protocol + registry + `SubscriberCursorStore` (+ table in the migration).
3. `dispatch_events` (cursor advance, error isolation, retry cap) + unit tests with fake subscribers.
4. `Notification` domain + `NotificationRow`/repo + UoW wiring + migration (notifications table, `UNIQUE(source_seq)`).
5. `NotificationSubscriber` + register it + integration test (events → notifications, idempotency, isolation).
6. Notification API (`GET /notifications`, mark-read) + camelCase contract + API tests.
7. `dispatch_events` Celery Beat task + wiring (schedule alongside `drain_bus`).
