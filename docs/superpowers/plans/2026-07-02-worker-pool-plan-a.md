# Containerized Worker Pool — Plan A (Pooled Worker + Safe Claiming)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the agent worker as a role-configured, scalable Docker service that claims only the bus messages for the role(s) it is configured to run.

**Architecture:** Add a `naaf_worker_roles` setting; make the message bus's `claim_next` role-aware (keeping the existing `FOR UPDATE SKIP LOCKED`); thread the worker's roles through `BusSource`; add a `Dockerfile` + a scalable `worker` service to `docker-compose`. Roles partition across workers (one role → one worker), which preserves the existing one-in-flight-per-recipient guarantee without new locking.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (sync), Celery, Postgres/SQLite, pytest, Docker + docker-compose.

## Global Constraints

- **Immutability:** Pydantic models updated via `model_copy(update={...})`; never mutate.
- **Persistence isolation:** ALL SQLAlchemy access lives ONLY in `adapters/database` / `adapters/bus` (the bus adapter is where the claim query lives).
- **Back-compat:** `claim_next(roles=None)` must preserve today's behavior (claim any pending message) — the `notifications` subscription and existing tests must be unaffected.
- **Concurrency invariant:** "one message in-flight per recipient (`run:<id>:<role>`)". This plan preserves it by **partitioning roles across workers — each role is assigned to exactly one worker**. Hardening for *multiple workers sharing a role* (a Postgres advisory lock per recipient) is a documented **follow-up**, out of scope here.
- **IDs / recipients:** bus messages carry a first-class `role` column and recipient key `run:<id>:<role>` — the role filter uses the `role` column directly (no parsing, no schema change).
- **Settings:** env prefix `naaf_`.
- **TDD:** failing test first; AAA; descriptive names. `make coverage` (80%) + `make lint` green before PR. Commands from repo root (`make …`) or `cd projects/server && uv run …`.

---

## File Structure

- Modify `projects/server/src/interactors/api/settings.py` — add `worker_roles` + `worker_roles_list`.
- Modify `projects/server/src/adapters/bus/ports.py` — `claim_next` gains `roles` param.
- Modify `projects/server/src/adapters/bus/sql.py` — role filter in `claim_next`.
- Modify `projects/server/src/interactors/worker/bus_source.py` — `BusSource(roles)`; pass to `claim_next`.
- Modify `projects/server/src/interactors/worker/registry.py` — build `BusSource` with `Settings().worker_roles_list`.
- Create `Dockerfile` (repo root) — server image (Python 3.12 + git + uv), worker entrypoint.
- Modify `docker-compose.yml` — add a scalable `worker` service.
- Create `docs/run-worker-pool.md` — run-book (scale, role-partition constraint, advisory-lock follow-up).
- Tests: `projects/server/tests/api/test_settings.py` (new), `projects/server/tests/adapters/bus/test_sql_bus.py` (extend/new), `projects/server/tests/interactors/worker/test_bus_source.py` (extend).

---

## Task 1: `naaf_worker_roles` setting

**Files:**
- Modify: `projects/server/src/interactors/api/settings.py`
- Test: `projects/server/tests/api/test_settings.py`

**Interfaces:**
- Produces: `Settings.worker_roles: str = ""` and `Settings.worker_roles_list -> list[str]` (comma-separated, trimmed, empties dropped).

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/api/test_settings.py
from interactors.api.settings import Settings


def test_worker_roles_list_parses_csv():
    assert Settings(worker_roles="lead, backend ,qa").worker_roles_list == ["lead", "backend", "qa"]


def test_worker_roles_list_empty_by_default():
    assert Settings().worker_roles_list == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_settings.py -v`
Expected: FAIL — `Settings` has no `worker_roles` / `worker_roles_list`.

- [ ] **Step 3: Add the field + parser**

In `settings.py`, add to `Settings`:

```python
    worker_roles: str = ""

    @property
    def worker_roles_list(self) -> list[str]:
        return [r.strip() for r in self.worker_roles.split(",") if r.strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/api/test_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/settings.py projects/server/tests/api/test_settings.py
git commit -m "feat: add naaf_worker_roles setting"
```

---

## Task 2: Role-filtered `claim_next`

**Files:**
- Modify: `projects/server/src/adapters/bus/ports.py`
- Modify: `projects/server/src/adapters/bus/sql.py` (`claim_next`)
- Test: `projects/server/tests/adapters/bus/test_sql_bus.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `MessageBus.claim_next(roles: list[str] | None = None) -> AgentMessage | None`. When `roles` is a non-empty list, only messages whose `role` ∈ `roles` are claimed; `None`/empty claims any (back-compat). `FOR UPDATE SKIP LOCKED` + the busy-recipient exclusion are unchanged.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/bus/test_sql_bus.py
import pytest
from adapters.bus.sql import SqlMessageBus
from adapters.database.orm import Base
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def _publish(bus, role):
    bus.publish(AgentMessage(owner_id="u1", run_id="r1", recipient=recipient_key("r1", role),
                             role=role, type=MessageType.START))


def test_claim_next_filters_by_role(session):
    bus = SqlMessageBus(session)
    _publish(bus, "lead")
    _publish(bus, "backend")
    claimed = bus.claim_next(["backend"])
    assert claimed is not None and claimed.role == "backend"


def test_claim_next_no_roles_claims_any(session):
    bus = SqlMessageBus(session)
    _publish(bus, "lead")
    claimed = bus.claim_next()
    assert claimed is not None and claimed.role == "lead"


def test_claim_next_returns_none_when_no_matching_role(session):
    bus = SqlMessageBus(session)
    _publish(bus, "lead")
    assert bus.claim_next(["qa"]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/bus/test_sql_bus.py -v`
Expected: FAIL — `claim_next()` takes no `roles` argument.

- [ ] **Step 3: Add the `roles` param to the port**

In `ports.py`, change the protocol method:

```python
    def claim_next(self, roles: list[str] | None = None) -> AgentMessage | None: ...
```

- [ ] **Step 4: Implement the filter in `sql.py`**

Replace `claim_next` with (the only change is the `roles` param + the `role IN` clause):

```python
    def claim_next(self, roles: list[str] | None = None) -> AgentMessage | None:
        """Claim the next pending message for processing.

        FOR UPDATE SKIP LOCKED prevents two workers claiming the SAME row. The
        one-in-flight-per-recipient invariant additionally relies on roles being
        partitioned across workers (one role → one worker); a Postgres advisory
        lock per recipient is the follow-up for multiple workers sharing a role.
        """
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/adapters/bus/test_sql_bus.py -v`
Expected: PASS (3 passed). Then run the existing bus/worker tests to confirm back-compat:
`cd projects/server && uv run pytest tests/adapters/bus tests/interactors/worker -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/adapters/bus/ports.py projects/server/src/adapters/bus/sql.py projects/server/tests/adapters/bus/test_sql_bus.py
git commit -m "feat: role-filtered claim_next on the message bus"
```

---

## Task 3: `BusSource` claims for the worker's configured roles

**Files:**
- Modify: `projects/server/src/interactors/worker/bus_source.py` (`BusSource.__init__`, `fetch_next`)
- Modify: `projects/server/src/interactors/worker/registry.py` (build `BusSource` with settings)
- Test: `projects/server/tests/interactors/worker/test_bus_source.py`

**Interfaces:**
- Consumes: `MessageBus.claim_next(roles)` (Task 2); `Settings.worker_roles_list` (Task 1).
- Produces: `BusSource(roles: list[str] | None = None)`; `fetch_next` claims only `roles`. The `agent-bus` subscription builds `BusSource(Settings().worker_roles_list or None)`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/interactors/worker/test_bus_source.py
from adapters.database.uow import SqlUnitOfWork
from adapters.bus.factory import build_message_bus
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from interactors.worker.bus_source import BusSource


def _publish(session_factory, role):
    s = session_factory()
    build_message_bus(s).publish(AgentMessage(owner_id="u1", run_id="r1",
        recipient=recipient_key("r1", role), role=role, type=MessageType.START))
    s.commit()
    s.close()


def test_bus_source_only_fetches_configured_roles(session_factory):
    _publish(session_factory, "lead")
    _publish(session_factory, "backend")
    source = BusSource(roles=["backend"])
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        item = source.fetch_next(uow)
    assert item is not None and item.message.role == "backend"
```

(Uses the shared `session_factory` fixture already in `tests/`. If it is not visible from this path, mirror the SQLite in-memory `session_factory` fixture used by `tests/adapters/bus`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_bus_source.py::test_bus_source_only_fetches_configured_roles -v`
Expected: FAIL — `BusSource()` takes no `roles` argument.

- [ ] **Step 3: Add `roles` to `BusSource`**

In `bus_source.py`, add the constructor and pass roles to `claim_next`:

```python
class BusSource:
    def __init__(self, roles: list[str] | None = None) -> None:
        self._roles = roles or None

    def fetch_next(self, uow) -> Item | None:
        msg = build_message_bus(uow.session).claim_next(self._roles)
        if msg is None:
            return None
        return Item(message=msg, owner_id=msg.owner_id, position=0)
```

(Leave `advance` / `on_poison` unchanged.)

- [ ] **Step 4: Wire the registry to read settings**

In `registry.py`, import `Settings` and build `BusSource` with the configured roles:

```python
from interactors.api.settings import Settings
# ... in SUBSCRIPTIONS, replace source_factory=BusSource with:
        source_factory=lambda: BusSource(Settings().worker_roles_list or None),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/interactors/worker -q`
Expected: PASS (new test + existing worker tests; default `worker_roles=""` → `None` → claim any, so existing pipeline tests are unaffected).

- [ ] **Step 6: Commit**

```bash
git add projects/server/src/interactors/worker/bus_source.py projects/server/src/interactors/worker/registry.py projects/server/tests/interactors/worker/test_bus_source.py
git commit -m "feat: BusSource claims only the worker's configured roles"
```

---

## Task 4: Dockerfile + `worker` compose service + run-book

**Files:**
- Create: `Dockerfile` (repo root)
- Modify: `docker-compose.yml`
- Create: `docs/run-worker-pool.md`

**Interfaces:**
- Produces: a buildable server image whose default command runs the Celery worker+beat; a scalable `worker` compose service configured by `naaf_worker_roles`.

> Infra task — verified by `docker compose config` (and `docker build` where Docker is available) + review, not pytest.

- [ ] **Step 1: Create the `Dockerfile`**

```dockerfile
# Dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY projects/server ./projects/server
RUN uv sync --frozen --no-dev

WORKDIR /app/projects/server
# Celery worker + beat (matches the Makefile `worker` target)
CMD ["uv", "run", "celery", "-A", "interactors.worker.celery_app:celery_app", "worker", "--beat", "--loglevel=info"]
```

- [ ] **Step 2: Add the `worker` service to `docker-compose.yml`**

Append under `services:`:

```yaml
  worker:
    build: .
    depends_on:
      - postgres
      - redis
    environment:
      naaf_db_url: postgresql+psycopg://naaf:naaf@postgres:5432/naaf
      naaf_celery_broker_url: redis://redis:6379/0
      naaf_worker_roles: "lead,architect,backend,frontend,qa,devops"
```

(Match the existing `postgres` credentials/db name in the file; adjust the `naaf_db_url` to them.)

- [ ] **Step 3: Write the run-book**

Create `docs/run-worker-pool.md` documenting:
- `docker compose up -d postgres redis && make db-upgrade` then `docker compose up --build worker`.
- **Scaling by role (the invariant):** to run multiple workers, give each a DISJOINT `naaf_worker_roles` so each role is served by exactly one worker — this preserves one-in-flight-per-recipient. Example: one worker `naaf_worker_roles=lead,qa`, another `naaf_worker_roles=backend,frontend`.
- **Do NOT** run two workers with an overlapping role until the per-recipient advisory-lock hardening lands (documented follow-up) — overlapping roles can double-process a recipient.

- [ ] **Step 4: Verify the compose config parses**

Run: `docker compose config -q`
Expected: exits 0 (valid). If Docker is available, also `docker build -t naaf-worker .` should succeed.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml docs/run-worker-pool.md
git commit -m "feat: containerized worker service + run-book"
```

---

## Task 5: Gates + docs note

**Files:**
- Modify: `docs/project-history.md`

- [ ] **Step 1: Backend gate**

Run: `cd /Users/noel/projects/naaf/.worktrees/worker-pool-sandbox && make coverage && make lint`
Expected: coverage ≥80%, ruff + mypy clean.

- [ ] **Step 2: Note the slice**

Add one bullet under the status area of `docs/project-history.md`: the worker now runs as a role-configured, scalable Docker service that claims only its configured roles from the bus (roles partitioned one-per-worker); the workspace + real-PR path is Plan B; egress hardening is deferred.

- [ ] **Step 3: Commit**

```bash
git add docs/project-history.md
git commit -m "docs: record containerized worker pool (Plan A)"
```

---

## Self-Review Notes (author)

- **Spec coverage (Plan A portion):** role-configured pool via compose (T4) ✓; role-filtered claiming (T2) + BusSource wiring (T3) ✓; `naaf_worker_roles` (T1) ✓; Dockerfile + scalable service (T4) ✓. Spec's "SKIP LOCKED" is already present in `claim_next`; the plan adds the role filter and documents the role-partition invariant (Global Constraints) since SKIP LOCKED alone does not preserve per-recipient one-in-flight — the advisory-lock hardening is called out as a follow-up (not a silent gap).
- **Deferred to Plan B:** `LocalWorkspace` adapter, `Scm`/GitHub App, `PROVISION`/`PR` wiring, `Run.pr_url`/`RunOut.prUrl` + monitor link. Deferred to slice 3: egress. Deferred to A5 checkpoint: `LlmAgentRuntime` wiring.
- **Type consistency:** `claim_next(roles: list[str] | None)` identical across ports.py (T2) → sql.py (T2) → BusSource (T3); `worker_roles_list` defined once (T1) and consumed in the registry (T3).
- **Back-compat:** default `worker_roles=""` → `None` → claim-any, so the `notifications` subscription and all existing pipeline/bus tests are unaffected (verified in T2/T3 steps).
- **Known infra caveat:** T4 verification needs Docker; where unavailable, verify via `docker compose config -q` + Dockerfile review, and confirm the image build in the manual run-book.
