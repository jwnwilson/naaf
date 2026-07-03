# Move Bus SQL into a Repository (UoW Pattern) — Design

**Date:** 2026-07-03
**Status:** Approved (design) — ready for implementation plan
**Type:** Refactor (architecture compliance) — no behavior change
**Branch:** `refactor/bus-repository`, stacked on `feat/worker-e2e` (PR #27); retarget base to `main` after #27 merges.

## Summary

`adapters/bus/sql.py` (`SqlMessageBus`) contains raw SQLAlchemy — violating the project rule
that **all SQLAlchemy access lives only in `adapters/database` repositories**. Move that SQL
into a **`BusMessageRepository`** and make the bus adapter a thin `MessageBus`-port delegator
that goes through the **UnitOfWork** (`uow.bus_messages`). Pure refactor: identical behavior,
same tests green.

`orm.py:120` even documents the smell: *"accessed directly by the SqlMessageBus adapter, not
via a UoW repository."* This closes it.

## Background & the critical constraint

The bus is a **cross-owner work queue**:
- The subscription engine drains it with an **unscoped** UoW — `SqlUnitOfWork(session_factory)`
  with no `required_filters` (`subscription_runner.uow_factory`); `claim_next` scans pending
  messages across **all** owners.
- `owner_id` on a bus message is *data* (used to build the per-item owner-scoped `HandlerContext`),
  **not** a scoping filter for bus operations.

Therefore the bus repository **must not apply owner-scoping** — unlike `runs`/`notifications`.
There is precedent: `SubscriberCursorRepository` already takes just a `session` and is not
owner-scoped. `BusMessageRepository` follows that shape.

## Goals

1. No SQLAlchemy in `adapters/bus/` — the bus adapter contains zero `select`/ORM/session-query code.
2. A `BusMessageRepository` in `adapters/database/` owns the bus SQL (`publish` / `claim_next(roles)`
   / `ack` + row↔`AgentMessage` mapping), cross-owner (not owner-scoped).
3. The bus adapter uses the **UoW pattern** — `SqlMessageBus` delegates to `uow.bus_messages`.
4. Behavior unchanged: `SKIP LOCKED` (non-sqlite) + busy-recipient exclusion + role filter +
   one-in-flight-per-recipient all preserved; every existing bus/worker/pipeline test still passes.

## Non-Goals

- No change to the `MessageBus` port signature (`publish`/`claim_next(roles)`/`ack`) — callers
  and the port are unchanged in shape.
- No new queue backend, no owner-scoping added to the bus, no change to the subscription engine
  or handlers beyond the `build_message_bus` call-site signature.

## Design

### `BusMessageRepository` (`adapters/database/repositories.py`)
```
class BusMessageRepository:
    def __init__(self, session: Session) -> None: ...          # cross-owner; no required_filters
    def publish(self, msg: AgentMessage) -> None: ...          # session.add(BusMessageRow(...)) + flush
    def claim_next(self, roles: list[str] | None = None) -> AgentMessage | None: ...
    def ack(self, msg: AgentMessage) -> None: ...
    def _to_msg(self, row: BusMessageRow) -> AgentMessage: ...
```
All the SQL currently in `SqlMessageBus` moves here **verbatim** (the `select`, `notin_(busy)`,
`role.in_(roles)`, `with_for_update(skip_locked=True)`, `session.get`, mapping). Co-located with
`SubscriberCursorRepository` (the sibling non-owner-scoped repo).

### `SqlMessageBus` (`adapters/bus/sql.py`) — thin delegator
```
class SqlMessageBus:
    def __init__(self, uow: SqlUnitOfWork) -> None:
        self._uow = uow
    def publish(self, msg):    self._uow.bus_messages.publish(msg)
    def claim_next(self, roles=None): return self._uow.bus_messages.claim_next(roles)
    def ack(self, msg):        self._uow.bus_messages.ack(msg)
```
No SQLAlchemy imports. Implements the `MessageBus` port. (If nothing else remains in the adapter,
this is acceptable — the port/adapter seam keeps the backend swappable per `factory.py`.)

### UoW (`adapters/database/uow.py`)
Add:
```
@property
def bus_messages(self) -> BusMessageRepository:
    return self._repo("bus_messages", BusMessageRepository)
```
`_repo` passes `required_filters` to the ctor — but `BusMessageRepository.__init__` takes only
`session`. Resolve by giving it a compatible signature that ignores scope, e.g.
`__init__(self, session, required_filters=None)` and simply not using `required_filters`
(documented: the bus is cross-owner). This keeps `_repo(...)` uniform. (Mirror how the plan
chooses; the key requirement is the repo never filters by owner.)

### Factory + call sites
- `build_message_bus(uow: SqlUnitOfWork) -> MessageBus` (was `(session)`) → `SqlMessageBus(uow)`.
- Update the 3 call sites to pass the UoW instead of `uow.session`:
  - `interactors/api/deps.py::get_bus` — `build_message_bus(uow)`.
  - `interactors/worker/subscription_runner.py::ctx_factory` — `bus=build_message_bus(uow)`.
  - `interactors/worker/bus_source.py` — `fetch_next`/`advance`/`on_poison` already receive `uow`; call `build_message_bus(uow)`.
- Remove/fix the `orm.py:120` comment (now accessed via a repository).

### Tests
- Move the bus SQL behavior tests to target `BusMessageRepository` directly (`tests/adapters/database/test_bus_message_repository.py`) — the role filter, no-roles-claims-any, no-match→None, publish/claim/ack round-trip, busy-recipient exclusion.
- Keep a thin `SqlMessageBus` delegation test (build a UoW, publish→claim→ack via the adapter) proving the port still works end-to-end.
- Update `tests/adapters/bus/test_sql_bus.py` + `tests/interactors/worker/test_bus_source.py` to the new construction (`build_message_bus(uow)` / `SqlMessageBus(uow)`), or relocate as above.

## Error handling
- `ack` on a missing id still raises (unchanged `RuntimeError`).
- Transaction boundaries are unchanged — the repo shares the UoW's session; `publish`/`claim`/`ack`
  flush within the caller's `uow.transaction()` exactly as today (atomicity preserved).

## Testing / acceptance
- `make coverage` (80%) + `make lint` (ruff + mypy) green.
- `grep -rn "select\|session\.\|BusMessageRow\|with_for_update" projects/server/src/adapters/bus` → nothing (no SQL left in the bus adapter).
- All existing bus/worker/pipeline tests pass unchanged in behavior.

## Open questions

None blocking. The exact `BusMessageRepository.__init__` signature (whether to accept an ignored
`required_filters` for `_repo` uniformity, or add the repo via a bespoke UoW accessor) is settled
in the plan; the binding requirement is that the bus repository never applies owner-scoping.
