# A3 Agent Run Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build NAAF's run pipeline spine — start a run on a work-item and a worker drives `PLAN → [✋plan gate] → IMPLEMENT → VERIFY → [✋merge gate] → PR → LEARN` via a durable Postgres message bus with scripted `FakeAgentRuntime` agents, persisting a run + stage timeline + append-only events, observable over the run API + SSE.

**Architecture:** Pure domain (`Run`/`RunEvent`/`Gate` + a `next_step` state machine) + a durable `MessageBus` (Postgres, per-agent queues drained sequentially) + a worker (`process_next`) that dispatches bus messages to lead/engineer/QA handlers which run stages via the `AgentRuntime` port. Local-First, no Temporal, no real LLM (A5) / sandbox (A4) / memory (A6) — `PROVISION/PR/LEARN` are stubs.

**Tech Stack:** Python 3.12 / `uv` / FastAPI / Pydantic v2 / SQLAlchemy 2.0 / Alembic / Postgres (SQLite in tests) / pytest / `sse-starlette` for SSE.

## Global Constraints

- `uv`; `make coverage` (80% gate) + `make lint` (ruff + mypy) stay green. Run backend commands from repo root; the Makefile is at root.
- **Hexagonal:** domain (`domain/`) is pure — no I/O, no adapter imports. Persistence ports live with their impl in `adapters/`. Wiring in `interactors/`.
- **Immutability:** Pydantic models updated via `model_copy(update={...})`, never mutated.
- **Envelope:** every JSON response is `{success, data, error}` (+ `meta` for lists); SSE is the one streaming exception. Contract is **camelCase** (A2-4 pattern); read `projects/ui/src/lib/api/schema.d.ts` for the exact `Run`/`AgentRun`/`Agent`/event shapes before writing a contract DTO.
- **Owner scoping:** runs + run_events carry `owner_id`; the UoW applies it as a required filter. The bus is worker-internal (claimed globally); each `bus_messages` row carries `owner_id` so the worker opens an owner-scoped context to process it.
- **Status set** (work items): `backlog/todo/in_progress/in_review/done`; all transitions go through `domain.transitions.validate_transition`.
- **Run status set:** `queued/running/awaiting_gate/succeeded/failed/cancelled`. **Stages:** `plan/provision/implement/verify/pr/learn`. **Autonomy:** `gated_all/gated_merge/full_auto`.
- IDs are 32-char UUID hex (`domain.base.new_id`). TDD: failing test first, AAA, descriptive names. Commits `<type>: <description>`, one per task.
- Work in the `feat/a3-run-pipeline` worktree at `.worktrees/a3-run-pipeline`.

---

## File Structure

```
projects/server/src/
  domain/
    runs/
      run.py          # RunStatus, Stage, StageStatus, StageState, GateKind, Gate, Run
      events.py       # EventType, RunEvent
      messages.py     # MessageType, MessageStatus, AgentMessage, recipient_key()
      gates.py        # requires_plan_gate(), requires_merge_gate()
      pipeline.py     # Step union + next_step(run, result); _next_stage, _gate_after
      coupling.py     # work_item_status_for(run) -> target status | None
    agent/
      runtime.py      # AgentEvent, StageResult, StageOutcome, AgentRuntime port
  adapters/
    database/
      orm.py          # + RunRow, RunEventRow, BusMessageRow
      repositories.py # + RunRepository, RunEventRepository
      repository.py   # (RunEventRepository overrides create to assign seq)
      uow.py          # + runs, run_events properties
      ports.py        # + runs, run_events on the UnitOfWork protocol
      migrations/versions/0003_runs.py
    bus/
      ports.py        # MessageBus protocol
      sql.py          # SqlMessageBus (publish/claim_next/ack)
    agent/runtime/
      fake.py         # FakeAgentRuntime
  interactors/
    worker/
      handlers.py     # HandlerContext + lead/engineer/qa handlers + advance()
      processor.py    # process_next(session_factory, bus, runtime) -> bool
      main.py         # while-True entrypoint (make worker)
    api/
      contract.py     # + RunOut, RunEventOut, GateDecisionIn (camelCase)
      routes/runs.py  # run API + SSE + gate
      routes/__init__.py  # register runs_router
```

---

### Task 1: Run domain model

**Files:**
- Create: `projects/server/src/domain/runs/__init__.py` (empty), `projects/server/src/domain/runs/run.py`
- Test: `projects/server/tests/domain/runs/__init__.py` (empty), `projects/server/tests/domain/runs/test_run.py`

**Interfaces:**
- Produces: `RunStatus`, `Stage`, `StageStatus`, `GateKind` (StrEnums); `StageState`, `Gate` (BaseModel); `Run(Entity)` with fields `owner_id: str`, `work_item_id: str`, `project_id: str`, `autonomy_level: str`, `status: RunStatus = QUEUED`, `current_stage: Stage | None = None`, `stages: list[StageState] = []`, `pending_gate: Gate | None = None`, `resolved_gates: list[GateKind] = []`, `verify_attempts: int = 0`, `max_verify_loops: int = 3`, `started_at: datetime | None = None`, `ended_at: datetime | None = None`.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/runs/test_run.py`:
```python
from domain.runs.run import GateKind, Run, RunStatus, Stage, StageState, StageStatus


def test_run_defaults():
    r = Run(owner_id="u1", work_item_id="w1", project_id="p1", autonomy_level="gated_all")
    assert r.status is RunStatus.QUEUED
    assert r.current_stage is None
    assert r.stages == []
    assert r.pending_gate is None
    assert r.resolved_gates == []
    assert r.verify_attempts == 0
    assert r.max_verify_loops == 3


def test_stage_state_and_enums():
    s = StageState(stage=Stage.PLAN, status=StageStatus.RUNNING, role="lead")
    assert s.stage is Stage.PLAN
    assert Stage.IMPLEMENT.value == "implement"
    assert GateKind.MERGE.value == "merge"


def test_run_is_immutable_via_model_copy():
    r = Run(owner_id="u1", work_item_id="w1", project_id="p1", autonomy_level="full_auto")
    r2 = r.model_copy(update={"status": RunStatus.RUNNING})
    assert r.status is RunStatus.QUEUED
    assert r2.status is RunStatus.RUNNING
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/domain/runs/test_run.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `run.py`**

```python
from datetime import datetime
from enum import StrEnum

from domain.base import Entity
from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_GATE = "awaiting_gate"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Stage(StrEnum):
    PLAN = "plan"
    PROVISION = "provision"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    PR = "pr"
    LEARN = "learn"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    GATED = "gated"


class GateKind(StrEnum):
    PLAN = "plan"
    MERGE = "merge"


class StageState(BaseModel):
    stage: Stage
    status: StageStatus = StageStatus.PENDING
    role: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Gate(BaseModel):
    kind: GateKind
    stage: Stage


class Run(Entity):
    owner_id: str
    work_item_id: str
    project_id: str
    autonomy_level: str
    status: RunStatus = RunStatus.QUEUED
    current_stage: Stage | None = None
    stages: list[StageState] = Field(default_factory=list)
    pending_gate: Gate | None = None
    resolved_gates: list[GateKind] = Field(default_factory=list)
    verify_attempts: int = 0
    max_verify_loops: int = 3
    started_at: datetime | None = None
    ended_at: datetime | None = None
```

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/domain/runs/test_run.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/runs projects/server/tests/domain/runs
git commit -m "feat: Run domain model + run/stage/gate enums"
```

---

### Task 2: RunEvent + AgentMessage models

**Files:**
- Create: `projects/server/src/domain/runs/events.py`, `projects/server/src/domain/runs/messages.py`
- Test: `projects/server/tests/domain/runs/test_events.py`

**Interfaces:**
- Produces:
  - `events.EventType` (StrEnum: `RUN_STARTED/STAGE_STARTED/LOG/STAGE_PASSED/STAGE_FAILED/GATE_REQUESTED/GATE_RESOLVED/RUN_FINISHED`); `events.RunEvent(Entity)` — `owner_id: str`, `run_id: str`, `seq: int = 0`, `stage: Stage | None = None`, `role: str | None = None`, `type: EventType`, `payload: dict = {}`.
  - `messages.MessageType` (StrEnum: `START/RUN_STAGE/STAGE_REPORT/GATE_RESOLVED`); `messages.MessageStatus` (StrEnum: `PENDING/CLAIMED/DONE`); `messages.recipient_key(run_id, role) -> str` returns `f"run:{run_id}:{role}"`; `messages.AgentMessage(BaseModel)` — `id: str = Field(default_factory=new_id)`, `owner_id`, `run_id`, `recipient: str`, `role: str`, `type: MessageType`, `payload: dict = {}`, `status: MessageStatus = PENDING`, `created_at: datetime = Field(default_factory=utcnow)`, `claimed_at: datetime | None = None`.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/runs/test_events.py`:
```python
from domain.runs.events import EventType, RunEvent
from domain.runs.messages import AgentMessage, MessageStatus, MessageType, recipient_key
from domain.runs.run import Stage


def test_run_event_defaults():
    e = RunEvent(owner_id="u1", run_id="r1", type=EventType.LOG, role="lead", stage=Stage.PLAN)
    assert e.seq == 0
    assert e.payload == {}
    assert e.type is EventType.LOG


def test_recipient_key_and_message():
    assert recipient_key("r1", "engineer") == "run:r1:engineer"
    m = AgentMessage(owner_id="u1", run_id="r1", recipient="run:r1:lead",
                     role="lead", type=MessageType.START)
    assert m.status is MessageStatus.PENDING
    assert m.id  # auto id
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/domain/runs/test_events.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`events.py`:
```python
from enum import StrEnum

from domain.base import Entity
from domain.runs.run import Stage
from pydantic import Field


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    LOG = "log"
    STAGE_PASSED = "stage_passed"
    STAGE_FAILED = "stage_failed"
    GATE_REQUESTED = "gate_requested"
    GATE_RESOLVED = "gate_resolved"
    RUN_FINISHED = "run_finished"


class RunEvent(Entity):
    owner_id: str
    run_id: str
    seq: int = 0
    stage: Stage | None = None
    role: str | None = None
    type: EventType
    payload: dict = Field(default_factory=dict)
```

`messages.py`:
```python
from datetime import datetime
from enum import StrEnum

from domain.base import new_id, utcnow
from pydantic import BaseModel, Field


class MessageType(StrEnum):
    START = "start"
    RUN_STAGE = "run_stage"
    STAGE_REPORT = "stage_report"
    GATE_RESOLVED = "gate_resolved"


class MessageStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    DONE = "done"


def recipient_key(run_id: str, role: str) -> str:
    return f"run:{run_id}:{role}"


class AgentMessage(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    recipient: str
    role: str
    type: MessageType
    payload: dict = Field(default_factory=dict)
    status: MessageStatus = MessageStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    claimed_at: datetime | None = None
```

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/domain/runs/test_events.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/runs/events.py projects/server/src/domain/runs/messages.py projects/server/tests/domain/runs/test_events.py
git commit -m "feat: RunEvent + AgentMessage domain models"
```

---

### Task 3: Gates + stage state machine (`next_step`)

**Files:**
- Create: `projects/server/src/domain/runs/gates.py`, `projects/server/src/domain/runs/pipeline.py`
- Test: `projects/server/tests/domain/runs/test_pipeline.py`

**Interfaces:**
- Consumes: `Run`, `Stage`, `GateKind`, `RunStatus` (Task 1).
- Produces:
  - `gates.requires_plan_gate(autonomy_level: str) -> bool` (`== "gated_all"`); `gates.requires_merge_gate(autonomy_level: str) -> bool` (`in {"gated_all","gated_merge"}`).
  - `pipeline.Advance(stage: Stage)`, `pipeline.GateStep(kind: GateKind)`, `pipeline.Retry(stage: Stage)`, `pipeline.Finish(status: RunStatus)` (frozen dataclasses); `Step = Advance | GateStep | Retry | Finish`.
  - `pipeline.next_step(run: Run, result: StageResult) -> Step` — pure (`result` is the just-completed stage's outcome; see Task 4 for `StageResult`, but `next_step` only reads `result.passed: bool`).

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/runs/test_pipeline.py`:
```python
from dataclasses import dataclass

from domain.runs.pipeline import Advance, Finish, GateStep, Retry, next_step
from domain.runs.run import GateKind, Run, RunStatus, Stage


@dataclass
class R:  # minimal stand-in for StageResult (next_step reads .passed only)
    passed: bool


def _run(stage, autonomy="gated_all", **kw):
    return Run(owner_id="u", work_item_id="w", project_id="p",
               autonomy_level=autonomy, current_stage=stage, **kw)


def test_plan_passed_requests_plan_gate_when_gated_all():
    assert next_step(_run(Stage.PLAN), R(True)) == GateStep(GateKind.PLAN)


def test_plan_gate_skipped_when_gated_merge():
    assert next_step(_run(Stage.PLAN, "gated_merge"), R(True)) == Advance(Stage.PROVISION)


def test_resolved_plan_gate_advances():
    r = _run(Stage.PLAN, resolved_gates=[GateKind.PLAN])
    assert next_step(r, R(True)) == Advance(Stage.PROVISION)


def test_provision_and_implement_advance():
    assert next_step(_run(Stage.PROVISION), R(True)) == Advance(Stage.IMPLEMENT)
    assert next_step(_run(Stage.IMPLEMENT), R(True)) == Advance(Stage.VERIFY)


def test_verify_passed_requests_merge_gate():
    assert next_step(_run(Stage.VERIFY), R(True)) == GateStep(GateKind.MERGE)


def test_verify_passed_full_auto_advances_to_pr():
    assert next_step(_run(Stage.VERIFY, "full_auto"), R(True)) == Advance(Stage.PR)


def test_verify_failed_retries_implement_until_limit():
    assert next_step(_run(Stage.VERIFY, verify_attempts=0), R(False)) == Retry(Stage.IMPLEMENT)
    assert next_step(_run(Stage.VERIFY, verify_attempts=3, max_verify_loops=3), R(False)) == Finish(RunStatus.FAILED)


def test_merge_gate_resolved_then_pr_learn_finish():
    r = _run(Stage.VERIFY, resolved_gates=[GateKind.MERGE])
    assert next_step(r, R(True)) == Advance(Stage.PR)
    assert next_step(_run(Stage.PR), R(True)) == Advance(Stage.LEARN)
    assert next_step(_run(Stage.LEARN), R(True)) == Finish(RunStatus.SUCCEEDED)
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/domain/runs/test_pipeline.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`gates.py`:
```python
def requires_plan_gate(autonomy_level: str) -> bool:
    return autonomy_level == "gated_all"


def requires_merge_gate(autonomy_level: str) -> bool:
    return autonomy_level in {"gated_all", "gated_merge"}
```

`pipeline.py`:
```python
from dataclasses import dataclass

from domain.runs.gates import requires_merge_gate, requires_plan_gate
from domain.runs.run import GateKind, Run, RunStatus, Stage

_ORDER = [Stage.PLAN, Stage.PROVISION, Stage.IMPLEMENT, Stage.VERIFY, Stage.PR, Stage.LEARN]


@dataclass(frozen=True)
class Advance:
    stage: Stage


@dataclass(frozen=True)
class GateStep:
    kind: GateKind


@dataclass(frozen=True)
class Retry:
    stage: Stage


@dataclass(frozen=True)
class Finish:
    status: RunStatus


Step = Advance | GateStep | Retry | Finish


def _next_stage(stage: Stage) -> Stage | None:
    i = _ORDER.index(stage)
    return _ORDER[i + 1] if i + 1 < len(_ORDER) else None


def _gate_after(stage: Stage, autonomy: str) -> GateKind | None:
    if stage is Stage.PLAN and requires_plan_gate(autonomy):
        return GateKind.PLAN
    if stage is Stage.VERIFY and requires_merge_gate(autonomy):
        return GateKind.MERGE
    return None


def next_step(run: Run, result) -> Step:
    """Pure transition: given the just-completed stage's result, what's next?

    `result` only needs a `.passed: bool` attribute.
    """
    current = run.current_stage
    if current is Stage.VERIFY and not result.passed:
        if run.verify_attempts < run.max_verify_loops:
            return Retry(Stage.IMPLEMENT)
        return Finish(RunStatus.FAILED)

    gate = _gate_after(current, run.autonomy_level)
    if gate is not None and gate not in run.resolved_gates and run.pending_gate is None:
        return GateStep(gate)

    nxt = _next_stage(current)
    if nxt is None:
        return Finish(RunStatus.SUCCEEDED)
    return Advance(nxt)
```

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/domain/runs/test_pipeline.py -v && make lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/runs/gates.py projects/server/src/domain/runs/pipeline.py projects/server/tests/domain/runs/test_pipeline.py
git commit -m "feat: run pipeline state machine + autonomy gates"
```

---

### Task 4: AgentRuntime port + FakeAgentRuntime

**Files:**
- Create: `projects/server/src/domain/agent/__init__.py` (empty), `projects/server/src/domain/agent/runtime.py`, `projects/server/src/adapters/agent/__init__.py` (empty), `projects/server/src/adapters/agent/runtime/__init__.py` (empty), `projects/server/src/adapters/agent/runtime/fake.py`
- Test: `projects/server/tests/adapters/agent/test_fake_runtime.py`

**Interfaces:**
- Produces:
  - `domain.agent.runtime.AgentEvent(BaseModel)` — `type: str = "log"`, `message: str`; `StageResult(BaseModel)` — `passed: bool`, `summary: str = ""`; `StageOutcome(BaseModel)` — `events: list[AgentEvent] = []`, `result: StageResult`; `AgentRuntime(Protocol)` — `run_stage(self, role: str, stage: Stage, ctx: dict) -> StageOutcome`.
  - `adapters.agent.runtime.fake.FakeAgentRuntime` — `__init__(self, fail_verify_times: int = 0)`; `run_stage(role, stage, ctx)` returns scripted events + a passing `StageResult`, EXCEPT when `stage is Stage.VERIFY` and the current attempt (`ctx["verify_attempts"]`) is `< fail_verify_times`, in which case `result.passed = False`.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/adapters/agent/test_fake_runtime.py`:
```python
from adapters.agent.runtime.fake import FakeAgentRuntime
from domain.runs.run import Stage


def test_fake_passes_by_default_and_emits_events():
    rt = FakeAgentRuntime()
    out = rt.run_stage("lead", Stage.PLAN, ctx={})
    assert out.result.passed is True
    assert len(out.events) >= 1
    assert all(e.message for e in out.events)


def test_fake_verify_fails_then_passes():
    rt = FakeAgentRuntime(fail_verify_times=1)
    first = rt.run_stage("qa", Stage.VERIFY, ctx={"verify_attempts": 0})
    second = rt.run_stage("qa", Stage.VERIFY, ctx={"verify_attempts": 1})
    assert first.result.passed is False
    assert second.result.passed is True
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_fake_runtime.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`domain/agent/runtime.py`:
```python
from typing import Protocol

from domain.runs.run import Stage
from pydantic import BaseModel, Field


class AgentEvent(BaseModel):
    type: str = "log"
    message: str


class StageResult(BaseModel):
    passed: bool
    summary: str = ""


class StageOutcome(BaseModel):
    events: list[AgentEvent] = Field(default_factory=list)
    result: StageResult


class AgentRuntime(Protocol):
    def run_stage(self, role: str, stage: Stage, ctx: dict) -> StageOutcome: ...
```

`adapters/agent/runtime/fake.py`:
```python
from domain.agent.runtime import AgentEvent, StageOutcome, StageResult
from domain.runs.run import Stage

_SCRIPT = {
    Stage.PLAN: ["Reading ticket + project memory", "Drafting implementation plan", "Plan ready (plan.md)"],
    Stage.PROVISION: ["Provisioning workspace (stub)"],
    Stage.IMPLEMENT: ["Checked out agent branch", "Editing files", "Committed changes"],
    Stage.VERIFY: ["Running tests", "Checking acceptance criteria"],
    Stage.PR: ["Would open PR (stub)"],
    Stage.LEARN: ["Distilling run into memory (stub)"],
}


class FakeAgentRuntime:
    """Scripted, no-LLM runtime. Passes every stage, except VERIFY can be made
    to fail the first `fail_verify_times` attempts to exercise the retry path."""

    def __init__(self, fail_verify_times: int = 0):
        self.fail_verify_times = fail_verify_times

    def run_stage(self, role: str, stage: Stage, ctx: dict) -> StageOutcome:
        events = [AgentEvent(message=m) for m in _SCRIPT.get(stage, [f"{stage.value} step"])]
        passed = True
        if stage is Stage.VERIFY and ctx.get("verify_attempts", 0) < self.fail_verify_times:
            passed = False
        summary = "ok" if passed else "verification failed"
        return StageOutcome(events=events, result=StageResult(passed=passed, summary=summary))
```

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_fake_runtime.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/agent projects/server/src/adapters/agent projects/server/tests/adapters/agent
git commit -m "feat: AgentRuntime port + FakeAgentRuntime"
```

---

### Task 5: ORM rows + Run/RunEvent repos + UoW wiring

**Files:**
- Modify: `projects/server/src/adapters/database/orm.py`, `repositories.py`, `repository.py`, `uow.py`, `ports.py`
- Test: `projects/server/tests/adapters/database/test_run_repository.py`

**Interfaces:**
- Consumes: `Run`, `RunEvent` (Tasks 1–2), the `SqlRepository`/`_Timestamped` patterns.
- Produces: `RunRow`, `RunEventRow`, `BusMessageRow` (ORM); `RunRepository`, `RunEventRepository` (the latter overrides `create` to assign a per-run monotonic `seq`); `uow.runs`, `uow.run_events`; `UnitOfWork.runs`/`.run_events` on the protocol.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/adapters/database/test_run_repository.py` (mirror the existing repo tests — use the `session_factory` fixture from conftest):
```python
from adapters.database.uow import SqlUnitOfWork
from domain.runs.events import EventType, RunEvent
from domain.runs.run import Run


def _uow(session_factory):
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})


def test_run_round_trips(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        r = uow.runs.create(Run(owner_id="", work_item_id="w1", project_id="p1", autonomy_level="gated_all"))
        got = uow.runs.read(r.id)
    assert got.work_item_id == "w1"
    assert got.owner_id == "u1"  # stamped
    assert got.status.value == "queued"


def test_run_event_seq_is_monotonic_per_run(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        e1 = uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        e2 = uow.run_events.create(RunEvent(owner_id="", run_id="r1", type=EventType.LOG))
        e3 = uow.run_events.create(RunEvent(owner_id="", run_id="r2", type=EventType.LOG))
    assert (e1.seq, e2.seq) == (1, 2)
    assert e3.seq == 1  # per-run counter resets
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_run_repository.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `orm.py` add (mirror `WorkItemRow` style; `_Timestamped` gives id/owner_id/created_at/updated_at):
```python
class RunRow(_Timestamped, Base):
    __tablename__ = "runs"
    work_item_id: Mapped[str] = mapped_column(String(32), ForeignKey("work_items.id"), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    autonomy_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    pending_gate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_gates: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    verify_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_verify_loops: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RunEventRow(_Timestamped, Base):
    __tablename__ = "run_events"
    run_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BusMessageRow(_Timestamped, Base):
    __tablename__ = "bus_messages"
    run_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    recipient: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```
(`pending_gate`/`stages`/`resolved_gates` are JSON; the repo's `_to_dto` builds the Pydantic model from columns — Pydantic coerces the dicts/lists back into `StageState`/`Gate`/enum values.)

In `repositories.py` add:
```python
from domain.runs.events import RunEvent
from domain.runs.run import Run
from adapters.database.orm import RunEventRow, RunRow
from sqlalchemy import func, select


class RunRepository(SqlRepository[Run]):
    orm_model = RunRow
    dto = Run


class RunEventRepository(SqlRepository[RunEvent]):
    orm_model = RunEventRow
    dto = RunEvent

    def create(self, dto):  # assign a per-run monotonic seq
        next_seq = self.session.execute(
            select(func.coalesce(func.max(RunEventRow.seq), 0) + 1).where(RunEventRow.run_id == dto.run_id)
        ).scalar_one()
        return super().create(dto.model_copy(update={"seq": next_seq}))
```

In `uow.py` add `runs`/`run_events` properties (mirror `projects`); in `ports.py` add `runs`/`run_events` to the `UnitOfWork` protocol.

- [ ] **Step 4: Run — passes (+ full suite)**

Run: `cd projects/server && uv run pytest && make lint`
Expected: PASS (SQLite `create_all` picks up the new tables).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database projects/server/tests/adapters/database/test_run_repository.py
git commit -m "feat: Run/RunEvent ORM rows + repos with per-run event seq"
```

---

### Task 6: Alembic migration (runs / run_events / bus_messages)

**Files:**
- Create: `projects/server/src/adapters/database/migrations/versions/0003_runs.py`
- Test: `projects/server/tests/adapters/test_migrations.py` (append)

**Interfaces:** Produces migration `0003_runs` (`down_revision = "0002_contract_fields"`) creating `runs`, `run_events`, `bus_messages` with the columns from Task 5.

- [ ] **Step 1: Append a migration test**

In `tests/adapters/test_migrations.py`:
```python
def test_migration_creates_run_tables(tmp_path):
    import os, sqlite3, subprocess
    from pathlib import Path
    db = tmp_path / "naaf.db"
    server = Path(__file__).resolve().parents[2]
    env = {"naaf_db_url": f"sqlite:///{db}", "PATH": os.environ["PATH"]}
    r = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=server, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db)
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "run_events", "bus_messages"} <= tables
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/adapters/test_migrations.py::test_migration_creates_run_tables -v`
Expected: FAIL.

- [ ] **Step 3: Write the migration**

Generate then edit:
```bash
cd projects/server
naaf_db_url="sqlite:////tmp/naaf_gen3.db" uv run alembic revision -m "runs" --rev-id 0003_runs
```
Set `down_revision = "0002_contract_fields"` and write `upgrade()` with three `op.create_table` calls matching the Task 5 columns (id `String(32)` PK; `owner_id` `String(64)` not null; `created_at`/`updated_at` `DateTime` not null; JSON columns via `sa.JSON()`; indexes on `runs.work_item_id`, `run_events.run_id`, `bus_messages.recipient`, `bus_messages.status`). `downgrade()` drops the three tables. Rename the generated file to `0003_runs.py` if alembic suffixed it; ensure `revision = "0003_runs"`. Delete the stray /tmp db.

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/adapters/test_migrations.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/migrations/versions/0003_runs.py projects/server/tests/adapters/test_migrations.py
git commit -m "feat: migration for runs/run_events/bus_messages"
```

---

### Task 7: Durable message bus (`MessageBus` port + SqlMessageBus)

**Files:**
- Create: `projects/server/src/adapters/bus/__init__.py` (empty), `projects/server/src/adapters/bus/ports.py`, `projects/server/src/adapters/bus/sql.py`
- Test: `projects/server/tests/adapters/bus/test_sql_bus.py`

**Interfaces:**
- Produces:
  - `ports.MessageBus(Protocol)` — `publish(self, msg: AgentMessage, session: Session) -> None`; `claim_next(self, session: Session) -> AgentMessage | None`; `ack(self, msg: AgentMessage, session: Session) -> None`.
  - `sql.SqlMessageBus` — implements the above against `BusMessageRow`. `claim_next` selects the oldest `pending` message whose `recipient` has **no** `claimed` (in-flight) message, marks it `claimed` (+`claimed_at`), and returns it as an `AgentMessage`. On Postgres use `.with_for_update(skip_locked=True)`; detect SQLite (`session.bind.dialect.name == "sqlite"`) and skip the locking clause (tests are single-threaded).

- [ ] **Step 1: Write the failing test**

`projects/server/tests/adapters/bus/test_sql_bus.py`:
```python
from adapters.bus.sql import SqlMessageBus
from domain.runs.messages import AgentMessage, MessageStatus, MessageType, recipient_key


def _msg(run="r1", role="lead", **kw):
    return AgentMessage(owner_id="u1", run_id=run, recipient=recipient_key(run, role),
                        role=role, type=MessageType.START, **kw)


def test_publish_claim_ack_roundtrip(session_factory):
    bus = SqlMessageBus()
    s = session_factory()
    bus.publish(_msg(), s); s.commit()
    claimed = bus.claim_next(s); s.commit()
    assert claimed is not None and claimed.status is MessageStatus.CLAIMED
    again = bus.claim_next(s); s.commit()  # one-in-flight-per-recipient
    assert again is None
    bus.ack(claimed, s); s.commit()
    assert bus.claim_next(s) is None  # nothing pending


def test_fifo_per_recipient_and_independent_recipients(session_factory):
    bus = SqlMessageBus()
    s = session_factory()
    bus.publish(_msg(role="lead"), s)
    bus.publish(_msg(role="engineer"), s); s.commit()
    a = bus.claim_next(s); s.commit()
    b = bus.claim_next(s); s.commit()  # different recipient → claimable
    assert {a.role, b.role} == {"lead", "engineer"}
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/adapters/bus/test_sql_bus.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`ports.py`:
```python
from typing import Protocol

from domain.runs.messages import AgentMessage
from sqlalchemy.orm import Session


class MessageBus(Protocol):
    def publish(self, msg: AgentMessage, session: Session) -> None: ...
    def claim_next(self, session: Session) -> AgentMessage | None: ...
    def ack(self, msg: AgentMessage, session: Session) -> None: ...
```

`sql.py`:
```python
from domain.base import utcnow
from domain.runs.messages import AgentMessage, MessageStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.database.orm import BusMessageRow


class SqlMessageBus:
    def publish(self, msg: AgentMessage, session: Session) -> None:
        session.add(BusMessageRow(
            id=msg.id, owner_id=msg.owner_id, run_id=msg.run_id, recipient=msg.recipient,
            role=msg.role, type=msg.type.value, payload=msg.payload, status=msg.status.value,
        ))
        session.flush()

    def claim_next(self, session: Session) -> AgentMessage | None:
        # recipients with an in-flight (claimed) message are blocked
        busy = select(BusMessageRow.recipient).where(BusMessageRow.status == "claimed")
        q = (select(BusMessageRow)
             .where(BusMessageRow.status == "pending", BusMessageRow.recipient.notin_(busy))
             .order_by(BusMessageRow.created_at).limit(1))
        if session.bind.dialect.name != "sqlite":
            q = q.with_for_update(skip_locked=True)
        row = session.execute(q).scalar_one_or_none()
        if row is None:
            return None
        row.status = "claimed"
        row.claimed_at = utcnow()
        session.flush()
        return self._to_msg(row)

    def ack(self, msg: AgentMessage, session: Session) -> None:
        row = session.get(BusMessageRow, msg.id)
        if row is not None:
            row.status = MessageStatus.DONE.value
            session.flush()

    def _to_msg(self, row: BusMessageRow) -> AgentMessage:
        return AgentMessage(id=row.id, owner_id=row.owner_id, run_id=row.run_id,
                            recipient=row.recipient, role=row.role, type=row.type,
                            payload=row.payload, status=row.status, created_at=row.created_at,
                            claimed_at=row.claimed_at)
```

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/adapters/bus/test_sql_bus.py && make lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/bus projects/server/tests/adapters/bus
git commit -m "feat: durable Postgres message bus (publish/claim/ack, FIFO per recipient)"
```

---

### Task 8: Work-item status coupling helper

**Files:**
- Create: `projects/server/src/domain/runs/coupling.py`
- Test: `projects/server/tests/domain/runs/test_coupling.py`

**Interfaces:**
- Produces: `coupling.work_item_status_for(run: Run) -> str | None` — the target work-item status implied by a run's state, or `None` if no change: `running`→`in_progress`; `awaiting_gate` with a `merge` pending gate→`in_review`; `succeeded`→`done`; `failed`/`cancelled`→`in_progress`; otherwise `None` (queued, plan-gate awaiting).

- [ ] **Step 1: Write the failing test**

`projects/server/tests/domain/runs/test_coupling.py`:
```python
from domain.runs.coupling import work_item_status_for
from domain.runs.run import Gate, GateKind, Run, RunStatus, Stage


def _run(status, **kw):
    return Run(owner_id="u", work_item_id="w", project_id="p", autonomy_level="gated_all", status=status, **kw)


def test_running_to_in_progress():
    assert work_item_status_for(_run(RunStatus.RUNNING)) == "in_progress"


def test_merge_gate_to_in_review():
    r = _run(RunStatus.AWAITING_GATE, pending_gate=Gate(kind=GateKind.MERGE, stage=Stage.VERIFY))
    assert work_item_status_for(r) == "in_review"


def test_plan_gate_no_change():
    r = _run(RunStatus.AWAITING_GATE, pending_gate=Gate(kind=GateKind.PLAN, stage=Stage.PLAN))
    assert work_item_status_for(r) is None


def test_succeeded_done_failed_in_progress():
    assert work_item_status_for(_run(RunStatus.SUCCEEDED)) == "done"
    assert work_item_status_for(_run(RunStatus.FAILED)) == "in_progress"
    assert work_item_status_for(_run(RunStatus.CANCELLED)) == "in_progress"
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/domain/runs/test_coupling.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
from domain.runs.run import GateKind, Run, RunStatus


def work_item_status_for(run: Run) -> str | None:
    if run.status is RunStatus.RUNNING:
        return "in_progress"
    if run.status is RunStatus.AWAITING_GATE and run.pending_gate is not None \
            and run.pending_gate.kind is GateKind.MERGE:
        return "in_review"
    if run.status is RunStatus.SUCCEEDED:
        return "done"
    if run.status in (RunStatus.FAILED, RunStatus.CANCELLED):
        return "in_progress"
    return None
```

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/domain/runs/test_coupling.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/runs/coupling.py projects/server/tests/domain/runs/test_coupling.py
git commit -m "feat: run -> work-item status coupling"
```

---

### Task 9: Worker handlers + orchestration (`handlers.py`)

**Files:**
- Create: `projects/server/src/interactors/worker/__init__.py` (empty), `projects/server/src/interactors/worker/handlers.py`
- Test: covered by the Task 11 integration test (handlers are exercised end-to-end through `process_next`); add a focused unit test here for `advance` stub-chaining.
- Test: `projects/server/tests/interactors/worker/test_handlers.py`

**Interfaces:**
- Consumes: `next_step`/`Advance`/`GateStep`/`Retry`/`Finish` (Task 3), `AgentRuntime` (Task 4), the repos + bus (Tasks 5/7), `work_item_status_for` (Task 8), `recipient_key`/`AgentMessage`/`MessageType` (Task 2).
- Produces:
  - `handlers.HandlerContext` (dataclass) — `runs`, `run_events`, `work_items` (repos), `bus`, `session`, `runtime`.
  - `handlers.dispatch(msg: AgentMessage, ctx: HandlerContext) -> None` — routes by `(msg.role, msg.type)` to `handle_lead` / `handle_engineer` / `handle_qa`.
  - Internal helpers: `emit(ctx, run, type, *, stage=None, role=None, payload=None)` (creates a RunEvent), `advance(ctx, run, result)` (the lead's loop), `couple(ctx, run)` (apply `work_item_status_for` via `validate_transition`).

- [ ] **Step 1: Write the failing test**

`projects/server/tests/interactors/worker/test_handlers.py` (unit: the lead's `advance` chains stub stages and stops at the engineer hand-off):
```python
from dataclasses import dataclass

import pytest
from adapters.agent.runtime.fake import FakeAgentRuntime
from domain.runs.run import Run, RunStatus, Stage
from interactors.worker import handlers


@dataclass
class FakeBus:
    published: list = None
    def __post_init__(self): self.published = []
    def publish(self, msg, session): self.published.append(msg)


class FakeRepo:
    def __init__(self): self.saved = {}
    def update(self, id, dto): self.saved[id] = dto; return dto
    def create(self, dto): self.saved[dto.id] = dto; return dto
    def read(self, id): return self.saved[id]


def test_advance_full_auto_chains_to_implement_handoff():
    # full_auto + current=PLAN passed → PROVISION(stub) → IMPLEMENT(handoff to engineer)
    run = Run(owner_id="u", work_item_id="w", project_id="p", autonomy_level="full_auto",
              status=RunStatus.RUNNING, current_stage=Stage.PLAN)
    runs = FakeRepo(); runs.create(run)
    wi = FakeRepo(); 
    ctx = handlers.HandlerContext(runs=runs, run_events=FakeRepo(), work_items=wi,
                                  bus=FakeBus(), session=None, runtime=FakeAgentRuntime())
    from domain.agent.runtime import StageResult
    handlers.advance(ctx, run, StageResult(passed=True))
    # stopped after publishing RUN_STAGE to the engineer; current stage is IMPLEMENT
    assert ctx.bus.published and ctx.bus.published[-1].role == "engineer"
    assert runs.read(run.id).current_stage is Stage.IMPLEMENT
```
(Note: `couple` calls `work_items.read`+`update`; for this unit test the work item isn't present, so guard `couple` to no-op when the work item is missing — but prefer seeding it. Seed `wi.create(...)` with a WorkItem in `in_progress` if your `couple` reads it; keep the test minimal and adjust to the real `couple` signature.)

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_handlers.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `handlers.py`**

```python
from dataclasses import dataclass
from typing import Any

from domain.agent.runtime import AgentRuntime, StageResult
from domain.runs.coupling import work_item_status_for
from domain.runs.events import EventType, RunEvent
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.pipeline import Advance, Finish, GateStep, Retry, next_step
from domain.runs.run import Gate, Run, RunStatus, Stage, StageState, StageStatus
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus
from domain.base import utcnow

_STUB_STAGES = {Stage.PROVISION, Stage.PR, Stage.LEARN}


@dataclass
class HandlerContext:
    runs: Any
    run_events: Any
    work_items: Any
    bus: Any
    session: Any
    runtime: AgentRuntime


def emit(ctx, run, type_, *, stage=None, role=None, payload=None):
    ctx.run_events.create(RunEvent(owner_id="", run_id=run.id, type=type_,
                                   stage=stage, role=role, payload=payload or {}))


def couple(ctx, run):
    target = work_item_status_for(run)
    if target is None:
        return
    wi = ctx.work_items.read(run.work_item_id)
    if wi.status.value == target:
        return
    new = validate_transition(wi.status, WorkItemStatus(target))
    ctx.work_items.update(wi.id, wi.model_copy(update={"status": new}))


def _save(ctx, run):
    ctx.runs.update(run.id, run)
    return run


def _run_stage_inline(ctx, run, role, stage) -> StageResult:
    run = _save(ctx, run.model_copy(update={"current_stage": stage}))
    emit(ctx, run, EventType.STAGE_STARTED, stage=stage, role=role)
    out = ctx.runtime.run_stage(role, stage, {"verify_attempts": run.verify_attempts})
    for ev in out.events:
        emit(ctx, run, EventType.LOG, stage=stage, role=role, payload={"message": ev.message})
    et = EventType.STAGE_PASSED if out.result.passed else EventType.STAGE_FAILED
    emit(ctx, run, et, stage=stage, role=role, payload={"summary": out.result.summary})
    return out.result


def advance(ctx, run, result):
    """Lead's control loop: act on next_step until it hands off / gates / finishes."""
    while True:
        step = next_step(run, result)
        if isinstance(step, Finish):
            run = _save(ctx, run.model_copy(update={"status": step.status, "ended_at": utcnow()}))
            emit(ctx, run, EventType.RUN_FINISHED, payload={"status": step.status.value})
            couple(ctx, run)
            return
        if isinstance(step, GateStep):
            gate = Gate(kind=step.kind, stage=run.current_stage)
            run = _save(ctx, run.model_copy(update={"status": RunStatus.AWAITING_GATE, "pending_gate": gate}))
            emit(ctx, run, EventType.GATE_REQUESTED, role="lead", payload={"kind": step.kind.value})
            couple(ctx, run)
            return
        if isinstance(step, Retry):  # VERIFY failed → re-run IMPLEMENT
            run = _save(ctx, run.model_copy(update={"verify_attempts": run.verify_attempts + 1,
                                                    "current_stage": Stage.IMPLEMENT}))
            _handoff(ctx, run, "engineer", Stage.IMPLEMENT)
            return
        # Advance
        stage = step.stage
        if stage is Stage.IMPLEMENT:
            run = _save(ctx, run.model_copy(update={"current_stage": stage}))
            _handoff(ctx, run, "engineer", stage)
            return
        if stage is Stage.VERIFY:
            run = _save(ctx, run.model_copy(update={"current_stage": stage}))
            _handoff(ctx, run, "qa", stage)
            return
        # stub stage handled inline by the lead, then keep looping
        result = _run_stage_inline(ctx, run, "lead", stage)
        run = ctx.runs.read(run.id)


def _handoff(ctx, run, role, stage):
    ctx.bus.publish(AgentMessage(owner_id=run.owner_id, run_id=run.id,
                                 recipient=recipient_key(run.id, role), role=role,
                                 type=MessageType.RUN_STAGE, payload={"stage": stage.value}), ctx.session)


def handle_lead(msg: AgentMessage, ctx: HandlerContext):
    run = ctx.runs.read(msg.run_id)
    if msg.type is MessageType.START:
        run = _save(ctx, run.model_copy(update={"status": RunStatus.RUNNING, "started_at": utcnow()}))
        emit(ctx, run, EventType.RUN_STARTED, role="lead")
        couple(ctx, run)
        result = _run_stage_inline(ctx, run, "lead", Stage.PLAN)
        run = ctx.runs.read(run.id)
        advance(ctx, run, result)
    elif msg.type is MessageType.STAGE_REPORT:
        result = StageResult(passed=bool(msg.payload.get("passed")), summary=msg.payload.get("summary", ""))
        advance(ctx, run, result)
    elif msg.type is MessageType.GATE_RESOLVED:
        if msg.payload.get("decision") == "approve":
            kind = run.pending_gate.kind
            run = _save(ctx, run.model_copy(update={
                "status": RunStatus.RUNNING, "pending_gate": None,
                "resolved_gates": [*run.resolved_gates, kind]}))
            emit(ctx, run, EventType.GATE_RESOLVED, role="lead", payload={"decision": "approve"})
            advance(ctx, run, StageResult(passed=True))
        else:
            run = _save(ctx, run.model_copy(update={"status": RunStatus.CANCELLED,
                                                    "pending_gate": None, "ended_at": utcnow()}))
            emit(ctx, run, EventType.GATE_RESOLVED, role="lead", payload={"decision": "reject"})
            emit(ctx, run, EventType.RUN_FINISHED, payload={"status": "cancelled"})
            couple(ctx, run)


def handle_engineer(msg, ctx):
    run = ctx.runs.read(msg.run_id)
    result = _run_stage_inline(ctx, run, "engineer", Stage.IMPLEMENT)
    _report(ctx, run, result)


def handle_qa(msg, ctx):
    run = ctx.runs.read(msg.run_id)
    result = _run_stage_inline(ctx, run, "qa", Stage.VERIFY)
    _report(ctx, run, result)


def _report(ctx, run, result):
    ctx.bus.publish(AgentMessage(owner_id=run.owner_id, run_id=run.id,
                                 recipient=recipient_key(run.id, "lead"), role="lead",
                                 type=MessageType.STAGE_REPORT,
                                 payload={"passed": result.passed, "summary": result.summary}), ctx.session)


def dispatch(msg: AgentMessage, ctx: HandlerContext):
    {"lead": handle_lead, "engineer": handle_engineer, "qa": handle_qa}[msg.role](msg, ctx)
```

(NOTE for the implementer: keep `emit`'s `owner_id=""` — the `RunEventRepository`/UoW stamps the owner from `required_filters`. Adjust the Step-1 unit test's `FakeRepo` so `couple` finds a seeded work item, or seed one; the real coverage of `advance` is the Task 11 integration test.)

- [ ] **Step 4: Run — passes (+ lint)**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_handlers.py && make lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker projects/server/tests/interactors/worker
git commit -m "feat: worker agent handlers + lead orchestration loop"
```

---

### Task 10: `process_next` + worker entrypoint

**Files:**
- Create: `projects/server/src/interactors/worker/processor.py`, `projects/server/src/interactors/worker/main.py`
- Modify: `Makefile` (add `worker` target)
- Test: `projects/server/tests/interactors/worker/test_processor.py`

**Interfaces:**
- Consumes: `SqlMessageBus`, `dispatch`/`HandlerContext` (Task 9), the repos.
- Produces: `processor.process_next(session_factory, bus, runtime) -> bool` — opens a session/transaction, claims one message, builds owner-scoped repos for `msg.owner_id`, dispatches, acks, commits; returns `True` if a message was processed, `False` if the queue was empty. `main.run_forever(...)` loops `process_next` with a short sleep when idle.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/interactors/worker/test_processor.py`:
```python
from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.sql import SqlMessageBus
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run
from interactors.worker.processor import process_next


def test_process_next_returns_false_when_empty(session_factory):
    assert process_next(session_factory, SqlMessageBus(), FakeAgentRuntime()) is False


def test_process_next_handles_a_start_message(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.create(Run(owner_id="", work_item_id="w1", project_id="p1", autonomy_level="full_auto"))
    bus, s = SqlMessageBus(), session_factory()
    bus.publish(AgentMessage(owner_id="u1", run_id=run.id, recipient=recipient_key(run.id, "lead"),
                             role="lead", type=MessageType.START), s)
    s.commit()
    assert process_next(session_factory, bus, FakeAgentRuntime()) is True
    # a RUN_STARTED event now exists for the run
    uow2 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow2.transaction():
        events = uow2.run_events.read_multi(filters={"run_id": run.id}).results
    assert any(e.type.value == "run_started" for e in events)
```
(This needs a work item `w1` for `couple`; create a Project+WorkItem first, or make `couple` tolerate a missing work item by catching `RecordNotFound`. Prefer seeding a real WorkItem `w1` in `in_progress`.)

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_processor.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`processor.py`:
```python
from adapters.database.repositories import RunEventRepository, RunRepository, WorkItemRepository
from interactors.worker.handlers import HandlerContext, dispatch


def process_next(session_factory, bus, runtime) -> bool:
    session = session_factory()
    try:
        msg = bus.claim_next(session)
        if msg is None:
            session.commit()
            return False
        scope = {"owner_id": msg.owner_id}
        ctx = HandlerContext(
            runs=RunRepository(session, required_filters=scope),
            run_events=RunEventRepository(session, required_filters=scope),
            work_items=WorkItemRepository(session, required_filters=scope),
            bus=bus, session=session, runtime=runtime,
        )
        dispatch(msg, ctx)
        bus.ack(msg, session)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

`main.py`:
```python
import time

from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.sql import SqlMessageBus
from adapters.database.engine import build_engine, build_session_factory
from interactors.api.settings import get_settings
from interactors.worker.processor import process_next

_IDLE_SLEEP_SECONDS = 0.5


def run_forever() -> None:
    settings = get_settings()
    session_factory = build_session_factory(build_engine(settings.db_url))
    bus, runtime = SqlMessageBus(), FakeAgentRuntime()
    while True:
        if not process_next(session_factory, bus, runtime):
            time.sleep(_IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    run_forever()
```
Add to `Makefile`:
```make
worker:
	cd projects/server && uv run python -m interactors.worker.main
```
(Verify `interactors/api/settings.get_settings` + `adapters/database/engine.build_session_factory` exist with those names; adjust imports to the real symbols.)

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_processor.py && make lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker/processor.py projects/server/src/interactors/worker/main.py Makefile projects/server/tests/interactors/worker/test_processor.py
git commit -m "feat: worker process_next + run-forever entrypoint (make worker)"
```

---

### Task 11: Full fake-pipeline integration test

**Files:**
- Test: `projects/server/tests/interactors/worker/test_pipeline_integration.py`

**Interfaces:** Consumes everything above. No new production code (if this test reveals a gap, fix it in the relevant module + note it).

- [ ] **Step 1: Write the integration test**

A helper drains the bus to quiescence (`while process_next(...): pass`), seeds a Project+WorkItem, starts a run by publishing a `START` message, then asserts behavior:
```python
from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.sql import SqlMessageBus
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run
from domain.work_item import WorkItem, WorkItemKind
from interactors.worker.processor import process_next


def _seed(session_factory, autonomy):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="", name="P", autonomy_level=autonomy))
        wi = uow.work_items.create(WorkItem(owner_id="", project_id=p.id, kind=WorkItemKind.TASK,
                                            title="T", status="todo"))
        run = uow.runs.create(Run(owner_id="", work_item_id=wi.id, project_id=p.id, autonomy_level=autonomy))
    return wi.id, run.id


def _drain(session_factory, bus, runtime):
    while process_next(session_factory, bus, runtime):
        pass


def _start(bus, session_factory, run_id):
    s = session_factory()
    bus.publish(AgentMessage(owner_id="u1", run_id=run_id, recipient=recipient_key(run_id, "lead"),
                             role="lead", type=MessageType.START), s)
    s.commit()


def _read_run(session_factory, run_id):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        return uow.runs.read(run_id), uow.run_events.read_multi(filters={"run_id": run_id}, page_size=0).results


def test_full_auto_run_succeeds_without_gates(session_factory):
    bus, rt = SqlMessageBus(), FakeAgentRuntime()
    wi_id, run_id = _seed(session_factory, "full_auto")
    _start(bus, session_factory, run_id)
    _drain(session_factory, bus, rt)
    run, events = _read_run(session_factory, run_id)
    assert run.status.value == "succeeded"
    assert {e.type.value for e in events} >= {"run_started", "stage_passed", "run_finished"}
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        assert uow.work_items.read(wi_id).status.value == "done"


def test_gated_all_pauses_at_plan_gate_then_resumes(session_factory):
    bus, rt = SqlMessageBus(), FakeAgentRuntime()
    _, run_id = _seed(session_factory, "gated_all")
    _start(bus, session_factory, run_id)
    _drain(session_factory, bus, rt)
    run, _ = _read_run(session_factory, run_id)
    assert run.status.value == "awaiting_gate" and run.pending_gate.kind.value == "plan"
    # approve the plan gate
    s = session_factory()
    bus.publish(AgentMessage(owner_id="u1", run_id=run_id, recipient=recipient_key(run_id, "lead"),
                             role="lead", type=MessageType.GATE_RESOLVED, payload={"decision": "approve"}), s)
    s.commit()
    _drain(session_factory, bus, rt)
    run, _ = _read_run(session_factory, run_id)
    # next pause is the merge gate
    assert run.status.value == "awaiting_gate" and run.pending_gate.kind.value == "merge"


def test_verify_retry_then_success(session_factory):
    bus, rt = SqlMessageBus(), FakeAgentRuntime(fail_verify_times=1)
    _, run_id = _seed(session_factory, "full_auto")
    _start(bus, session_factory, run_id)
    _drain(session_factory, bus, rt)
    run, events = _read_run(session_factory, run_id)
    assert run.status.value == "succeeded"
    assert run.verify_attempts == 1
    assert sum(1 for e in events if e.stage and e.stage.value == "implement" and e.type.value == "stage_started") >= 2
```

- [ ] **Step 2: Run — iterate to green**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_pipeline_integration.py -v`
Fix any gaps surfaced (in the owning module, not the test) until all three pass.

- [ ] **Step 3: Commit**

```bash
git add projects/server/tests/interactors/worker/test_pipeline_integration.py
git commit -m "test: full fake-pipeline integration (full_auto, gated_all, verify retry)"
```

---

### Task 12: Run contract DTOs + run API (start/get/list/gate)

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py`, `projects/server/src/interactors/api/routes/__init__.py`
- Create: `projects/server/src/interactors/api/routes/runs.py`
- Test: `projects/server/tests/api/test_runs_api.py`

**Interfaces:**
- Consumes: the run repos, the bus, `recipient_key`/`AgentMessage`/`MessageType`, `iso` (contract helper). Read `schema.d.ts` for the UI `Run`/`AgentRun`/`Agent`/event shapes and match field names.
- Produces (camelCase, inline-DTO style like the A2-4 routes):
  - `contract.RunOut` / `contract.RunEventOut` / `contract.GateDecisionIn` (`decision: Literal["approve","reject"]`).
  - `routes/runs.py`: module-level `router = APIRouter(tags=["runs"])` + `project_unscoped` (for `/runs`); endpoints `POST /work-items/{id}/runs`, `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events`, `POST /runs/{id}/gate`. `register_routers` includes it.

- [ ] **Step 1: Write the failing test**

`projects/server/tests/api/test_runs_api.py` (uses the `client` fixture):
```python
def _project_and_item(client, autonomy="full_auto"):
    pid = client.post("/projects/", json={"name": "P"}).json()["data"]["id"]
    # set autonomy via... (projects PATCH doesn't expose autonomy; create defaults gated_all)
    wid = client.post(f"/projects/{pid}/work-items", json={"type": "task", "title": "T"}).json()["data"]["id"]
    return pid, wid


def test_start_run_returns_camelcase_run(client):
    _, wid = _project_and_item(client)
    body = client.post(f"/work-items/{wid}/runs").json()
    d = body["data"]
    assert body["success"] and d["workItemId"] == wid
    assert d["status"] == "queued" and "createdAt" in d
    assert "owner_id" not in d


def test_list_and_get_run(client):
    _, wid = _project_and_item(client)
    rid = client.post(f"/work-items/{wid}/runs").json()["data"]["id"]
    listed = client.get(f"/runs?work_item={wid}").json()["data"]
    assert any(r["id"] == rid for r in listed)
    assert client.get(f"/runs/{rid}").json()["data"]["id"] == rid


def test_gate_endpoint_validates_decision(client):
    _, wid = _project_and_item(client)
    rid = client.post(f"/work-items/{wid}/runs").json()["data"]["id"]
    # no pending gate yet → 409 (or 422 if you choose); assert a clean error envelope
    r = client.post(f"/runs/{rid}/gate", json={"decision": "approve"})
    assert r.status_code in (409, 422)
```

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/api/test_runs_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add `RunOut`/`RunEventOut`/`GateDecisionIn` to `contract.py` (camelCase: `id`, `workItemId`, `projectId`, `status`, `currentStage`, `stages`, `createdAt`, `updatedAt`, `startedAt`, `endedAt`; map the stage timeline to the shape `schema.d.ts` expects). In `routes/runs.py` build a module-level router (mirror `routes/projects.py` style, `Depends(get_uow)` + a `_run_out(run)` local builder):
- `POST /work-items/{id}/runs`: read the work item (owner-scoped 404), read its project for `autonomy_level`, `uow.runs.create(Run(... autonomy_level=project.autonomy_level))`, then publish a `START` message to the lead via `SqlMessageBus().publish(..., uow.session)` (reuse the request session so it commits atomically), and transition the work item → `in_progress`. Return `RunOut` (201).
- `GET /runs?work_item=&project=&status=`: list (filters mapped like the work-items list), `RunOut[]`.
- `GET /runs/{id}`: `RunOut`.
- `GET /runs/{id}/events?after=<seq>`: `uow.run_events.read_multi(filters={"run_id": id, "seq__gt": after}, order_by="seq")` → `RunEventOut[]`.
- `POST /runs/{id}/gate` (`GateDecisionIn`): if the run has no `pending_gate` → raise `InvalidTransition`/409; else publish a `GATE_RESOLVED` message (payload `{"decision": ...}`) to the lead. Return the updated `RunOut` (status still `awaiting_gate` until the worker runs — that's fine).

Wire the run-start to use a shared bus instance. Register the router in `routes/__init__.py`.

- [ ] **Step 4: Run — passes (+ full suite + lint)**

Run: `cd projects/server && uv run pytest && make lint`
Expected: PASS; ruff+mypy clean. (Note: starting a run only *enqueues* — no worker runs in the API tests, so the run stays `queued`; that's expected.)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api projects/server/tests/api/test_runs_api.py
git commit -m "feat: run API (start/list/get/events/gate) emitting the UI contract"
```

---

### Task 13: SSE event stream

**Files:**
- Modify: `projects/server/src/interactors/api/routes/runs.py`, `projects/server/pyproject.toml` (add `sse-starlette`)
- Test: `projects/server/tests/api/test_runs_sse.py`

**Interfaces:**
- Produces: `GET /runs/{id}/events/stream` — an `text/event-stream` response that, starting after an optional `?after=<seq>` cursor, polls `run_events` for new rows on a short interval and yields each as an SSE `data:` JSON line (the `RunEventOut` shape), terminating after it emits a `run_finished` event (or after a max-duration safety cap).

- [ ] **Step 1: Write the failing test**

`projects/server/tests/api/test_runs_sse.py` — seed a run with a couple of events directly via the UoW, then assert the stream yields them. Use the TestClient streaming API:
```python
def test_sse_streams_existing_events_and_closes_on_finish(client, session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from domain.runs.events import EventType, RunEvent
    from domain.runs.run import Run
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        run = uow.runs.create(Run(owner_id="", work_item_id="w", project_id="p", autonomy_level="full_auto"))
        uow.run_events.create(RunEvent(owner_id="", run_id=run.id, type=EventType.LOG, payload={"message": "hi"}))
        uow.run_events.create(RunEvent(owner_id="", run_id=run.id, type=EventType.RUN_FINISHED, payload={"status": "succeeded"}))
    with client.stream("GET", f"/runs/{run.id}/events/stream") as resp:
        assert resp.status_code == 200
        body = "".join(chunk for chunk in resp.iter_text())
    assert "hi" in body
    assert "run_finished" in body
```
(The `client` fixture must share the same `session_factory` the test seeds into — confirm the conftest builds the app with the test session factory; if `client` and `session_factory` are independent, adapt to seed through the API or expose the app's factory.)

- [ ] **Step 2: Run — fails**

Run: `cd projects/server && uv run pytest tests/api/test_runs_sse.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add `sse-starlette` to `pyproject.toml` deps; `uv sync`. In `routes/runs.py`:
```python
from sse_starlette.sse import EventSourceResponse

_SSE_POLL_SECONDS = 0.25
_SSE_MAX_SECONDS = 600


@router.get("/runs/{id}/events/stream")
def stream_events(id: str, request: Request, after: int = 0, uow=Depends(get_uow)):  # noqa: B008
    def gen():
        cursor = after
        waited = 0.0
        while waited < _SSE_MAX_SECONDS:
            rows = uow.run_events.read_multi(filters={"run_id": id, "seq__gt": cursor},
                                             order_by="seq", page_size=0).results
            for ev in rows:
                cursor = ev.seq
                yield {"data": _run_event_out(ev).model_dump_json()}
                if ev.type.value == "run_finished":
                    return
            time.sleep(_SSE_POLL_SECONDS)
            waited += _SSE_POLL_SECONDS
    return EventSourceResponse(gen())
```
(`get_uow` yields within a transaction; for a long-lived stream, open a fresh short-lived UoW per poll instead of holding one transaction open — implement `gen()` to create a new `SqlUnitOfWork(request.app.state.session_factory, required_filters={"owner_id": owner})` per iteration and close it, so the stream doesn't pin a transaction. Resolve `owner` via the same auth dep the other routes use.)

- [ ] **Step 4: Run — passes**

Run: `cd projects/server && uv run pytest tests/api/test_runs_sse.py && make coverage && make lint`
Expected: PASS; coverage ≥80%; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/routes/runs.py projects/server/pyproject.toml projects/server/uv.lock projects/server/tests/api/test_runs_sse.py
git commit -m "feat: SSE run-event stream"
```

---

### Task 14: UI hybrid wiring + dev docs

**Files:**
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts` (move runs/agents/inbox handlers from `mockOnlyHandlers` to `liveHandlers`), `CLAUDE.md` (worker dev recipe)
- Test: `projects/ui/src/lib/api/mocks/handlers.test.ts` (update the split assertions)

**Interfaces:** Consumes the live run endpoints. Produces the runs/agents/inbox paths in `liveHandlers` so they hit the real backend under `VITE_LIVE_API`.

- [ ] **Step 1: Update the handler-split test**

In `handlers.test.ts`, assert the run/agent/inbox paths are now in `liveHandlers` (and removed from `mockOnlyHandlers`). Keep dashboard/budget mock-only (no backend yet).

- [ ] **Step 2: Run — fails**

Run: `cd projects/ui && pnpm test src/lib/api/mocks/handlers.test`
Expected: FAIL.

- [ ] **Step 3: Move the handlers + update CLAUDE.md**

Move the `/api/runs*`, `/api/work-items/:id/runs`, `/api/agents*` (if backed), and inbox handlers from `mockOnlyHandlers` to `liveHandlers`. Update the `CLAUDE.md` hybrid recipe to also start the worker: `make worker` (a third terminal) alongside the API.

- [ ] **Step 4: Full gates**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm build`
Then backend: `cd projects/server && make coverage && make lint`
Expected: all green.

- [ ] **Step 5: Manual end-to-end (document in the PR)**

```bash
# terminal 1: API   (cd projects/server; naaf_db_url=postgresql+psycopg://naaf:naaf@localhost:5432/naaf make run)
# terminal 2: worker(naaf_db_url=... make worker)
# terminal 3: UI    (cd projects/ui; VITE_LIVE_API=true pnpm dev)
```
Start a run on a work item from the UI; confirm the Agent-Monitor streams stage events, the plan gate appears in the inbox, approving it resumes the run, and the work-item status tracks `in_progress → in_review → done`.

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/lib/api/mocks CLAUDE.md
git commit -m "feat(ui): wire runs/agents/inbox to the live backend in hybrid mode"
```

---

## Self-Review

**1. Spec coverage:** §4.1 durable bus → Tasks 5(ORM)/6(migration)/7(SqlMessageBus). §4.2 worker → Tasks 9/10. §4.3 agent handlers → Task 9. §4.4 AgentRuntime+Fake → Task 4. §5 Run/event/gate model → Tasks 1/2. §6 `next_step` state machine + gates → Task 3. §7 work-item coupling → Task 8 (applied in Task 9). §8 API + gate → Task 12; SSE → Task 13. §9 persistence → Tasks 5/6. §10 testing → unit (1–4,8), adapter (5,7), integration (11), API/SSE (12/13). §2 contract alignment + UI hybrid → Tasks 12/14. No spec section is unimplemented.

**2. Placeholder scan:** No "TBD"/"implement later". The mechanical boilerplate (ORM rows, migration, route DTOs) ships with complete column/field lists + code; a few tasks instruct reading authoritative in-repo sources (`schema.d.ts` for exact contract field names; confirming `get_settings`/`build_session_factory` symbol names) rather than transcribing — consistent with A2-4. All logic-bearing code (state machine, bus claim, `process_next`, handlers, fake runtime, SSE generator) is complete with tests.

**3. Type consistency:** `Run`/`Stage`/`RunStatus`/`GateKind` (Task 1) are used identically in 3 (`next_step`), 5 (repos), 8 (coupling), 9 (handlers), 12 (API). `StageResult` (Task 4) is the `.passed` contract `next_step` (Task 3) and the handlers (Task 9) rely on. `AgentMessage`/`MessageType`/`recipient_key` (Task 2) are consumed by the bus (7), handlers (9), processor (10), API (12). `MessageBus.publish/claim_next/ack(…, session)` (Task 7) is the signature `process_next` (10) and the run-start route (12) call. `process_next(session_factory, bus, runtime) -> bool` (Task 10) is what the integration test (11) and `main` drive. `HandlerContext` fields (9) match what `process_next` (10) constructs. `work_item_status_for` (8) is applied by `couple` (9). Names are consistent across the plan.
