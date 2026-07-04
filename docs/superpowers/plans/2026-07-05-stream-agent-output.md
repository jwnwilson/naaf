# Stream Agent Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream an agent's full activity trace (streamed text + every tool call and result) into the chat and run-monitor UIs as it happens, replacing the ~60–90s of silence, and show a `…` typing indicator while a turn is in flight.

**Architecture:** The blocking `claude -p --output-format json` call becomes a streaming `--output-format stream-json --verbose` call whose NDJSON events are persisted (coarse-grained) to a new `agent_events` table as they arrive. A poll-based SSE endpoint tails that table (the exact pattern `/runs/{id}/events/stream` already uses). The UI reduces the event stream into a live activity feed + typing indicator. The database is the cross-process channel between the Celery worker and the FastAPI process — no Redis.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic (batch mode for SQLite), `sse-starlette`, Celery worker, Claude Code CLI (`claude -p`), React + Vite + React Query, `openapi-typescript`.

## Global Constraints

- Python ≥ 3.12, package manager `uv`; run backend commands from `projects/server`.
- Immutability: Pydantic models updated via `model_copy(update={...})`, never mutated.
- API envelope: every response is `{success, data, error}` (+ `meta` for pagination) via `ok(...)`.
- Owner scoping: every owned row carries `owner_id`; create with `owner_id=""` and it is stamped from the UnitOfWork's `required_filters` on the live path. Every repository query is owner-scoped.
- Entity/run IDs are UUID hex strings (32 chars). Scope keys (`thread:<id>` / `run:<id>`) fit in `String(64)`.
- TDD: write the failing test first; AAA structure; descriptive behavior names. Frequent commits.
- Gates before PR: `make coverage` (80% gate) + `make lint` (ruff + mypy) from repo root; `pnpm test` (vitest) from `projects/ui`.
- Alembic column/table changes that must work on SQLite use `op.batch_alter_table` / plain `op.create_table` (no `ALTER COLUMN TYPE`).
- Commit format: `<type>: <description>` (feat/fix/refactor/docs/test/chore).
- Keep files focused (<800 lines); prefer new small modules over growing large ones.

---

## Phase 1 — Backend foundation

### Task 1: `AgentEvent` domain model

**Files:**
- Create: `projects/server/src/domain/agent/events.py`
- Test: `projects/server/tests/domain/agent/test_agent_events.py`

**Interfaces:**
- Produces:
  - `AgentEvent(Entity)` with fields `owner_id: str`, `scope: str`, `seq: int = 0`, `kind: str`, `payload: dict = {}`.
  - Constants `EVENT_STATUS = "status"`, `EVENT_TEXT = "text_block"`, `EVENT_TOOL_CALL = "tool_call"`, `EVENT_TOOL_RESULT = "tool_result"`, `EVENT_FINAL = "final"`, `EVENT_ERROR = "error"`.
  - `def stream_scope(*, thread_id: str | None = None, run_id: str | None = None) -> str` → `f"thread:{thread_id}"` or `f"run:{run_id}"`; raises `ValueError` if neither/both provided.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/domain/agent/test_agent_events.py
import pytest

from domain.agent.events import (
    EVENT_STATUS,
    AgentEvent,
    stream_scope,
)


def test_stream_scope_builds_thread_key():
    assert stream_scope(thread_id="project:abc") == "thread:project:abc"


def test_stream_scope_builds_run_key():
    assert stream_scope(run_id="deadbeef") == "run:deadbeef"


def test_stream_scope_requires_exactly_one_target():
    with pytest.raises(ValueError):
        stream_scope()
    with pytest.raises(ValueError):
        stream_scope(thread_id="t", run_id="r")


def test_agent_event_defaults_are_immutable_friendly():
    ev = AgentEvent(owner_id="u1", scope="thread:t", kind=EVENT_STATUS)
    assert ev.seq == 0
    assert ev.payload == {}
    updated = ev.model_copy(update={"seq": 3})
    assert updated.seq == 3 and ev.seq == 0  # original unchanged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/agent/test_agent_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.agent.events'`

- [ ] **Step 3: Write minimal implementation**

```python
# projects/server/src/domain/agent/events.py
from pydantic import Field

from domain.base import Entity

EVENT_STATUS = "status"
EVENT_TEXT = "text_block"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_FINAL = "final"
EVENT_ERROR = "error"


class AgentEvent(Entity):
    """A coarse-grained, owner-scoped activity event streamed from an agent turn.

    ``scope`` is the stream key (``thread:<id>`` or ``run:<id>``); ``seq`` is a
    monotonic per-scope counter used for SSE replay/resume; ``payload`` carries
    text / tool name+args / result summary / usage / error depending on ``kind``.
    """

    owner_id: str
    scope: str
    seq: int = 0
    kind: str
    payload: dict = Field(default_factory=dict)


def stream_scope(*, thread_id: str | None = None, run_id: str | None = None) -> str:
    if bool(thread_id) == bool(run_id):
        raise ValueError("stream_scope requires exactly one of thread_id or run_id")
    return f"thread:{thread_id}" if thread_id else f"run:{run_id}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/domain/agent/test_agent_events.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/agent/events.py projects/server/tests/domain/agent/test_agent_events.py
git commit -m "feat: AgentEvent domain model + stream_scope helper"
```

---

### Task 2: `agent_events` table (ORM row + migration)

**Files:**
- Modify: `projects/server/src/adapters/database/orm.py` (add `AgentEventRow` after `RunEventRow`)
- Create: `projects/server/src/adapters/database/migrations/versions/0014_agent_events.py`
- Test: `projects/server/tests/adapters/database/test_agent_events_migration.py`

**Interfaces:**
- Produces: `AgentEventRow` (`__tablename__ = "agent_events"`), columns `id, owner_id, created_at, updated_at` (from `_Timestamped`) plus `scope: String(64)`, `seq: Integer`, `kind: String(16)`, `payload: JSON`. Unique constraint `(scope, seq)`; index on `scope`. Migration revision `"0014_agent_events"`, `down_revision = "0013_widen_message_thread_id"`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/database/test_agent_events_migration.py
from sqlalchemy import inspect

from adapters.database.orm import AgentEventRow


def test_agent_event_row_table_shape():
    cols = {c.name for c in AgentEventRow.__table__.columns}
    assert {"id", "owner_id", "scope", "seq", "kind", "payload", "created_at"} <= cols


def test_agent_events_table_created_by_metadata(session_factory):
    # session_factory fixture runs Base.metadata.create_all — table must exist.
    insp = inspect(session_factory().get_bind())
    assert "agent_events" in insp.get_table_names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_agent_events_migration.py -v`
Expected: FAIL with `ImportError: cannot import name 'AgentEventRow'`

- [ ] **Step 3a: Add the ORM row**

Insert into `projects/server/src/adapters/database/orm.py` immediately after the `RunEventRow` class:

```python
class AgentEventRow(_Timestamped, Base):
    __tablename__ = "agent_events"
    __table_args__ = (UniqueConstraint("scope", "seq"),)
    scope: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
```

- [ ] **Step 3b: Write the migration**

```python
# projects/server/src/adapters/database/migrations/versions/0014_agent_events.py
"""agent_events table for streamed agent activity

Revision ID: 0014_agent_events
Revises: 0013_widen_message_thread_id
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_agent_events"
down_revision = "0013_widen_message_thread_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_events",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "seq"),
    )
    op.create_index(op.f("ix_agent_events_owner_id"), "agent_events", ["owner_id"], unique=False)
    op.create_index(op.f("ix_agent_events_scope"), "agent_events", ["scope"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_events_scope"), table_name="agent_events")
    op.drop_index(op.f("ix_agent_events_owner_id"), table_name="agent_events")
    op.drop_table("agent_events")
```

- [ ] **Step 4: Run tests + migration check**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_agent_events_migration.py -v`
Expected: PASS (2 passed)

Run (verify migration applies + is reversible on SQLite): `cd projects/server && uv run pytest tests/adapters/database/ -k migration -v`
Expected: PASS (existing migration tests still green)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/orm.py projects/server/src/adapters/database/migrations/versions/0014_agent_events.py projects/server/tests/adapters/database/test_agent_events_migration.py
git commit -m "feat: agent_events table + migration 0014"
```

---

### Task 3: `AgentEventRepository` + UnitOfWork wiring

**Files:**
- Modify: `projects/server/src/adapters/database/repositories.py` (add `AgentEventRepository`; import `AgentEvent`, `AgentEventRow`)
- Modify: `projects/server/src/adapters/database/uow.py` (import + `agent_events` property)
- Modify: `projects/server/src/adapters/database/ports.py` (add `agent_events` to `UnitOfWork` protocol)
- Test: `projects/server/tests/adapters/database/test_agent_event_repository.py`

**Interfaces:**
- Consumes: `AgentEvent` (Task 1), `AgentEventRow` (Task 2), `SqlRepository`.
- Produces:
  - `AgentEventRepository(SqlRepository[AgentEvent])` with `orm_model = AgentEventRow`, `dto = AgentEvent`, an overridden `create(dto) -> AgentEvent` that computes the next per-`scope` `seq`, and `list_after(scope: str, after: int, limit: int = 200) -> list[AgentEvent]`.
  - `SqlUnitOfWork.agent_events -> AgentEventRepository`.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/database/test_agent_event_repository.py
from adapters.database.uow import SqlUnitOfWork
from domain.agent.events import EVENT_STATUS, EVENT_TEXT, AgentEvent


def _uow(session_factory):
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})


def test_create_assigns_monotonic_seq_per_scope(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        a = uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_STATUS))
        b = uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_TEXT))
        c = uow.agent_events.create(AgentEvent(owner_id="", scope="thread:OTHER", kind=EVENT_STATUS))
        assert (a.seq, b.seq) == (1, 2)
        assert c.seq == 1  # per-scope counter, independent of thread:t


def test_list_after_returns_only_newer_events_in_order(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_STATUS))
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_TEXT))
        rows = uow.agent_events.list_after("thread:t", after=1)
        assert [r.seq for r in rows] == [2]
        assert rows[0].kind == EVENT_TEXT


def test_owner_scoping_hides_other_owners_events(session_factory):
    with SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"}).transaction() as uow:
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:t", kind=EVENT_STATUS))
    with SqlUnitOfWork(session_factory, required_filters={"owner_id": "u2"}).transaction() as uow:
        assert uow.agent_events.list_after("thread:t", after=0) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_agent_event_repository.py -v`
Expected: FAIL with `AttributeError: 'SqlUnitOfWork' object has no attribute 'agent_events'`

- [ ] **Step 3a: Add the repository**

In `projects/server/src/adapters/database/repositories.py`, add `AgentEvent` to the domain imports, `AgentEventRow` to the orm imports, and add this class after `RunEventRepository`:

```python
class AgentEventRepository(SqlRepository[AgentEvent]):
    orm_model = AgentEventRow
    dto = AgentEvent

    def create(self, dto: AgentEvent) -> AgentEvent:  # type: ignore[override]
        q = select(func.coalesce(func.max(AgentEventRow.seq), 0) + 1).where(
            AgentEventRow.scope == dto.scope
        )
        for key, value in self.required_filters.items():
            q = q.where(getattr(AgentEventRow, key) == value)
        next_seq = self.session.execute(q).scalar_one()
        return super().create(dto.model_copy(update={"seq": next_seq}))

    def list_after(self, scope: str, after: int, limit: int = 200) -> list[AgentEvent]:
        page = self.read_multi(
            filters={"scope": scope, "seq__gt": after},
            order_by="seq",
            page_size=limit,
        )
        return page.results
```

- [ ] **Step 3b: Wire into the UnitOfWork**

In `projects/server/src/adapters/database/uow.py`, add `AgentEventRepository` to the imports and add this property after `run_events`:

```python
    @property
    def agent_events(self) -> AgentEventRepository:
        return self._repo("agent_events", AgentEventRepository)
```

In `projects/server/src/adapters/database/ports.py`, add to the `UnitOfWork` protocol after `run_events`:

```python
    @property
    def agent_events(self) -> Repository: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/database/test_agent_event_repository.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/database/repositories.py projects/server/src/adapters/database/uow.py projects/server/src/adapters/database/ports.py projects/server/tests/adapters/database/test_agent_event_repository.py
git commit -m "feat: AgentEventRepository with per-scope seq + list_after"
```

---

### Task 4: Streaming runner (parse `stream-json` NDJSON → emit events)

**Files:**
- Create: `projects/server/src/adapters/agent/claude_cli/stream_runner.py`
- Test: `projects/server/tests/adapters/agent/test_stream_runner.py`

**Interfaces:**
- Consumes: `EventSink` type (define here) — `EventSink = Callable[[str, dict], None]`.
- Produces:
  - `EventSink` type alias (imported by the adapter and worker).
  - `parse_stream_line(line: str) -> list[tuple[str, dict]]` — maps one NDJSON line to zero or more `(kind, payload)` pairs (pure, unit-testable).
  - `streaming_runner(argv, *, cwd=None, env=None, timeout=None, emit=None) -> dict` — runs `claude` via `Popen`, reads stdout line-by-line, calls `emit(kind, payload)` per parsed event, and returns the same dict shape as `_default_runner`: `{"result": str, "is_error": bool, "usage": dict}`. Accepts an injectable `_popen` for tests (default `subprocess.Popen`).

**Notes on the `claude --output-format stream-json` shape** (one JSON object per line):
- `{"type":"assistant","message":{"content":[{"type":"text","text":"…"}]}}` → `text_block`
- `{"type":"assistant","message":{"content":[{"type":"tool_use","name":"…","input":{…}}]}}` → `tool_call`
- `{"type":"user","message":{"content":[{"type":"tool_result","content":"…"}]}}` → `tool_result`
- `{"type":"result","result":"…","is_error":false,"usage":{…}}` → terminal (`final`)

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/agent/test_stream_runner.py
from adapters.agent.claude_cli.stream_runner import parse_stream_line, streaming_runner


def test_parse_text_block():
    line = '{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"}]}}'
    assert parse_stream_line(line) == [("text_block", {"text": "Hello"})]


def test_parse_tool_call():
    line = (
        '{"type":"assistant","message":{"content":['
        '{"type":"tool_use","name":"create_task","input":{"title":"x"}}]}}'
    )
    assert parse_stream_line(line) == [
        ("tool_call", {"name": "create_task", "input": {"title": "x"}})
    ]


def test_parse_tool_result():
    line = '{"type":"user","message":{"content":[{"type":"tool_result","content":"ok"}]}}'
    assert parse_stream_line(line) == [("tool_result", {"result": "ok"})]


def test_parse_result_line_is_terminal_not_an_event():
    line = '{"type":"result","result":"done","is_error":false,"usage":{"input_tokens":3}}'
    assert parse_stream_line(line) == []  # terminal handled by the runner, not emitted here


def test_parse_bad_line_is_ignored():
    assert parse_stream_line("not json") == []


class _FakeProc:
    def __init__(self, lines):
        self.stdout = iter(lines)
        self.returncode = 0

    def wait(self, timeout=None):
        return 0


def test_streaming_runner_emits_events_and_returns_final():
    lines = [
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Hi"}]}}\n',
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"list_board","input":{}}]}}\n',
        '{"type":"user","message":{"content":[{"type":"tool_result","content":"[]"}]}}\n',
        '{"type":"result","result":"all done","is_error":false,"usage":{"output_tokens":5}}\n',
    ]
    seen = []
    data = streaming_runner(
        ["claude"], emit=lambda k, p: seen.append((k, p)),
        _popen=lambda *a, **k: _FakeProc(lines),
    )
    assert [k for k, _ in seen] == ["text_block", "tool_call", "tool_result"]
    assert data["result"] == "all done"
    assert data["is_error"] is False
    assert data["usage"] == {"output_tokens": 5}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_stream_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.agent.claude_cli.stream_runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# projects/server/src/adapters/agent/claude_cli/stream_runner.py
"""Run headless Claude Code with --output-format stream-json and forward each
NDJSON event to a sink, returning the same final dict shape as _default_runner.
"""
import json
import subprocess
from collections.abc import Callable

EventSink = Callable[[str, dict], None]


def parse_stream_line(line: str) -> list[tuple[str, dict]]:
    """Map one NDJSON line to zero+ (kind, payload) events. The terminal
    ``result`` line returns [] — the runner assembles the final dict from it."""
    line = line.strip()
    if not line:
        return []
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return []
    kind = obj.get("type")
    events: list[tuple[str, dict]] = []
    if kind in ("assistant", "user"):
        for block in obj.get("message", {}).get("content", []):
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                events.append(("text_block", {"text": block["text"]}))
            elif btype == "tool_use":
                events.append(("tool_call", {"name": block.get("name", ""), "input": block.get("input", {})}))
            elif btype == "tool_result":
                events.append(("tool_result", {"result": block.get("content", "")}))
    return events


def streaming_runner(argv, *, cwd=None, env=None, timeout=None, emit=None, _popen=subprocess.Popen) -> dict:
    result_text = ""
    is_error = False
    usage: dict = {}
    try:
        proc = _popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        return {"is_error": True, "result": f"claude CLI not found ({argv[0]})", "usage": {}}
    try:
        for line in proc.stdout:  # blocks per line as claude emits them
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                obj = None
            if obj is not None and obj.get("type") == "result":
                result_text = str(obj.get("result", ""))
                is_error = bool(obj.get("is_error", False))
                usage = obj.get("usage") or {}
                continue
            if emit is not None:
                for kind, payload in parse_stream_line(line):
                    emit(kind, payload)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"is_error": True, "result": f"claude timed out after {timeout}s", "usage": {}}
    if proc.returncode not in (0, None) and not result_text:
        is_error = True
        result_text = f"claude exited {proc.returncode}"
    return {"result": result_text, "is_error": is_error, "usage": usage}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_stream_runner.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/agent/claude_cli/stream_runner.py projects/server/tests/adapters/agent/test_stream_runner.py
git commit -m "feat: claude stream-json streaming runner + line parser"
```

---

### Task 5: Adapter `set_event_sink` (use streaming runner when a sink is set)

**Files:**
- Modify: `projects/server/src/adapters/agent/claude_cli/adapter.py`
- Test: `projects/server/tests/adapters/agent/test_adapter_streaming.py`

**Interfaces:**
- Consumes: `EventSink`, `streaming_runner` (Task 4).
- Produces: `ClaudeCliLLMAdapter.set_event_sink(emit: EventSink | None) -> None`. When a sink is set, `complete()` builds argv with `--output-format stream-json --verbose` and calls the streaming runner with `emit=`; when unset, behavior is unchanged (blocking `--output-format json`). Backward compatible: injected non-streaming test runners are still called without an `emit` kwarg.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/agent/test_adapter_streaming.py
from adapters.agent.claude_cli.adapter import ClaudeCliLLMAdapter
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole


def _req():
    return LLMRequest(model="m", messages=[LLMMessage(role=MessageRole.USER, content="hi")])


def test_no_sink_uses_json_format_and_no_emit_kwarg():
    seen = {}

    def runner(argv, *, cwd=None, env=None, timeout=None):  # note: no emit kwarg
        seen["argv"] = argv
        return {"result": "ok", "usage": {}}

    ClaudeCliLLMAdapter(runner=runner).complete(_req())
    assert "--output-format" in seen["argv"]
    i = seen["argv"].index("--output-format")
    assert seen["argv"][i + 1] == "json"


def test_sink_switches_to_stream_json_and_forwards_emit():
    seen = {}

    def runner(argv, *, cwd=None, env=None, timeout=None, emit=None):
        seen["argv"] = argv
        emit("text_block", {"text": "streamed"})
        return {"result": "final", "usage": {}}

    events = []
    adapter = ClaudeCliLLMAdapter(runner=runner)
    adapter.set_event_sink(lambda k, p: events.append((k, p)))
    resp = adapter.complete(_req())
    i = seen["argv"].index("--output-format")
    assert seen["argv"][i + 1] == "stream-json"
    assert "--verbose" in seen["argv"]
    assert events == [("text_block", {"text": "streamed"})]
    assert resp.content == "final"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_adapter_streaming.py -v`
Expected: FAIL with `AttributeError: 'ClaudeCliLLMAdapter' object has no attribute 'set_event_sink'`

- [ ] **Step 3: Edit the adapter**

In `projects/server/src/adapters/agent/claude_cli/adapter.py`:

Add the import near the top:
```python
from adapters.agent.claude_cli.stream_runner import EventSink, streaming_runner
```

In `__init__`, add after `self._runner = ...`:
```python
        self._emit: EventSink | None = None
```

Add this method after `set_cwd`:
```python
    def set_event_sink(self, emit: EventSink | None) -> None:
        """Attach a per-call activity sink. When set, complete() streams events
        via claude's stream-json output (single-concurrency worker → safe)."""
        self._emit = emit
```

In `complete()`, replace the argv output-format section and the runner call. Change the argv builder so the format depends on streaming, and dispatch to the right runner:

```python
        streaming = self._emit is not None
        fmt = "stream-json" if streaming else "json"
        argv = [
            self._bin, "-p", self._prompt(request.messages),
            "--output-format", fmt, "--permission-mode", "bypassPermissions",
        ]
        if streaming:
            argv += ["--verbose"]  # claude requires --verbose with stream-json under -p
        if system:
            argv += ["--append-system-prompt", system]
        if self._cwd:
            argv += ["--add-dir", self._cwd]
        if self._mcp:
            argv += ["--mcp-config", self._mcp, "--allowed-tools", "mcp__naaf__*"]

        if streaming:
            runner = self._runner or streaming_runner
            data = runner(argv, cwd=self._cwd, env=self._env(), timeout=self._timeout, emit=self._emit)
        else:
            runner = self._runner or _default_runner
            data = runner(argv, cwd=self._cwd, env=self._env(), timeout=self._timeout)
```

(Leave the rest of `complete()` — the `has_report` / VERDICT synthesis and `LLMResponse` assembly — unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_adapter_streaming.py tests/adapters/agent/test_claude_oauth_secret.py -v`
Expected: PASS (all — new streaming tests + existing adapter tests still green)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/agent/claude_cli/adapter.py projects/server/tests/adapters/agent/test_adapter_streaming.py
git commit -m "feat: adapter set_event_sink streams via stream-json"
```

---

## Phase 2 — Wiring

### Task 6: `set_event_sink` passthrough on responder / orchestrator / runtime

**Files:**
- Modify: `projects/server/src/adapters/agent/chat/llm.py` (`LlmChatResponder`)
- Modify: `projects/server/src/adapters/agent/chat/orchestrator_llm.py` (`LlmOrchestrator`)
- Modify: `projects/server/src/domain/agent/runtime.py` (`LlmAgentRuntime`)
- Modify: `projects/server/src/adapters/agent/chat/echo.py`, `orchestrator_echo.py` (no-op `set_event_sink`)
- Test: `projects/server/tests/adapters/agent/test_event_sink_passthrough.py`

**Interfaces:**
- Produces: each of `LlmChatResponder`, `LlmOrchestrator`, `LlmAgentRuntime`, `EchoChatResponder`, `EchoOrchestrator` gains `set_event_sink(emit) -> None`. The LLM-backed variants forward to `self._llm.set_event_sink(emit)` if the adapter supports it; the echo/fake variants are no-ops. This keeps `respond()` / `run_stage()` signatures unchanged.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/adapters/agent/test_event_sink_passthrough.py
from adapters.agent.chat.echo import EchoChatResponder
from adapters.agent.chat.llm import LlmChatResponder


class _SinkAdapter:
    def __init__(self):
        self.sink = "unset"

    def set_event_sink(self, emit):
        self.sink = emit


def test_llm_responder_forwards_sink_to_adapter():
    adapter = _SinkAdapter()
    responder = LlmChatResponder(adapter)
    sentinel = lambda k, p: None
    responder.set_event_sink(sentinel)
    assert adapter.sink is sentinel


def test_echo_responder_set_event_sink_is_noop():
    EchoChatResponder().set_event_sink(lambda k, p: None)  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_event_sink_passthrough.py -v`
Expected: FAIL with `AttributeError: 'LlmChatResponder' object has no attribute 'set_event_sink'`

- [ ] **Step 3: Add the passthroughs**

Add this method to `LlmChatResponder` (`chat/llm.py`), `LlmOrchestrator` (`orchestrator_llm.py`), and `LlmAgentRuntime` (`domain/agent/runtime.py`):

```python
    def set_event_sink(self, emit) -> None:
        setter = getattr(self._llm, "set_event_sink", None)
        if setter is not None:
            setter(emit)
```

Add this no-op to `EchoChatResponder` (`chat/echo.py`) and `EchoOrchestrator` (`orchestrator_echo.py`):

```python
    def set_event_sink(self, emit) -> None:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/adapters/agent/test_event_sink_passthrough.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/adapters/agent/chat/llm.py projects/server/src/adapters/agent/chat/orchestrator_llm.py projects/server/src/domain/agent/runtime.py projects/server/src/adapters/agent/chat/echo.py projects/server/src/adapters/agent/chat/orchestrator_echo.py projects/server/tests/adapters/agent/test_event_sink_passthrough.py
git commit -m "feat: set_event_sink passthrough on responder/orchestrator/runtime"
```

---

### Task 7: Worker sink — persist activity events in chat handlers

**Files:**
- Modify: `projects/server/src/interactors/worker/handlers.py` (`HandlerContext.agent_events` field; `build_event_sink`; wire into `_handle_project_chat` + `handle_chat`)
- Modify: `projects/server/src/interactors/worker/subscription_runner.py` (build `agent_events` repo in `ctx_factory`)
- Test: `projects/server/tests/interactors/worker/test_chat_activity_events.py`

**Interfaces:**
- Consumes: `AgentEvent`, `EVENT_STATUS/EVENT_FINAL/EVENT_ERROR`, `stream_scope` (Task 1); `set_event_sink` (Task 6).
- Produces:
  - `HandlerContext.agent_events: Any = None`.
  - `build_event_sink(ctx: HandlerContext, scope: str) -> EventSink | None` — returns an `emit(kind, payload)` that calls `ctx.agent_events.create(AgentEvent(owner_id="", scope=scope, kind=kind, payload=payload))`, or `None` when `ctx.agent_events is None`.
  - Both chat handlers: emit `status` up front, attach the sink to the responder/orchestrator, emit `final` (or `error`) at the end.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/interactors/worker/test_chat_activity_events.py
from domain.agent.events import EVENT_FINAL, EVENT_STATUS
from domain.messaging.chat import ChatTurn
from domain.runs.messages import AgentMessage, MessageType
from interactors.worker.handlers import HandlerContext, build_event_sink, handle_chat


class _Recorder:
    def __init__(self):
        self.events = []

    def create(self, dto):
        self.events.append(dto)
        return dto


class _Responder:
    """Fake chat responder that drives the sink like the real streaming adapter."""
    def __init__(self):
        self._emit = None

    def set_event_sink(self, emit):
        self._emit = emit

    def respond(self, role, history, title):
        if self._emit:
            self._emit("text_block", {"text": "partial"})
        return "final reply"


class _Messages:
    def __init__(self):
        self.created = []

    def read_multi(self, **kw):
        class P:
            results: list = []
        return P()

    def create(self, dto):
        self.created.append(dto)
        return dto


def test_build_event_sink_persists_events_with_scope():
    rec = _Recorder()
    ctx = HandlerContext(runs=None, run_events=None, work_items=None, notifications=None,
                         bus=None, runtime=None, agent_events=rec)
    sink = build_event_sink(ctx, "thread:t")
    sink(EVENT_STATUS, {"state": "working"})
    assert rec.events[0].scope == "thread:t"
    assert rec.events[0].kind == EVENT_STATUS


def test_handle_chat_emits_status_then_final_around_reply(monkeypatch):
    rec = _Recorder()
    msgs = _Messages()
    ctx = HandlerContext(runs=None, run_events=None, work_items=None, notifications=None,
                         bus=None, runtime=None, agent_events=rec, messages=msgs,
                         chat_responder=_Responder())
    monkeypatch.setattr("interactors.worker.handlers._work_item_title_by_id", lambda c, w: "T")
    msg = AgentMessage(owner_id="u1", run_id="", recipient="wi:w1:backend", role="backend",
                       type=MessageType.CHAT, payload={"work_item_id": "w1", "depth": 0})
    handle_chat(msg, ctx)
    kinds = [e.kind for e in rec.events]
    assert kinds[0] == EVENT_STATUS
    assert EVENT_FINAL in kinds
    assert msgs.created and msgs.created[0].content == "final reply"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_chat_activity_events.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_event_sink'`

- [ ] **Step 3a: Add the field + helper + wiring in `handlers.py`**

Add to the imports:
```python
from domain.agent.events import EVENT_ERROR, EVENT_FINAL, EVENT_STATUS, AgentEvent, stream_scope
```

Add `agent_events` to the `HandlerContext` dataclass (after `run_events`):
```python
    agent_events: Any = None  # AgentEventRepository | None
```

Add the helper near `_post_agent_message`:
```python
def build_event_sink(ctx: "HandlerContext", scope: str):
    """Return an emit(kind, payload) that persists activity events, or None."""
    if ctx.agent_events is None:
        return None

    def emit(kind: str, payload: dict) -> None:
        ctx.agent_events.create(AgentEvent(owner_id="", scope=scope, kind=kind, payload=payload))

    return emit
```

In `_handle_project_chat`, wrap the orchestrator call:
```python
    scope = stream_scope(thread_id=thread_id)
    sink = build_event_sink(ctx, scope)
    if sink:
        sink(EVENT_STATUS, {"state": "working"})
        ctx.lead_orchestrator.set_event_sink(sink)
    try:
        reply_text = ctx.lead_orchestrator.respond(history, project.name, tools)
    finally:
        if sink:
            ctx.lead_orchestrator.set_event_sink(None)
    if sink:
        sink(EVENT_FINAL, {"text": reply_text})
    if reply_text.strip():
        _post_agent_message(ctx, thread_id, "lead", reply_text)
```

In `handle_chat` (work-item branch), wrap the responder call the same way:
```python
    scope = stream_scope(thread_id=thread_id)
    sink = build_event_sink(ctx, scope)
    if sink:
        sink(EVENT_STATUS, {"state": "working"})
        ctx.chat_responder.set_event_sink(sink)
    try:
        reply_text = ctx.chat_responder.respond(role, history, title)
    finally:
        if sink:
            ctx.chat_responder.set_event_sink(None)
    if sink:
        sink(EVENT_FINAL, {"text": reply_text})
    if not reply_text.strip():
        return
    _post_agent_message(ctx, work_item_id, role, reply_text)
    for target in plan_fanout(reply_text, depth + 1):
        _publish_chat(ctx, work_item_id, msg.owner_id, target, depth + 1)
```

- [ ] **Step 3b: Build the repo in `ctx_factory`**

In `projects/server/src/interactors/worker/subscription_runner.py`, inside `ctx_factory` where the other scoped repos are constructed for `HandlerContext`, add:
```python
            agent_events=AgentEventRepository(uow.session, required_filters=scope),
```
and add `AgentEventRepository` to the repositories import at the top of that file.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/interactors/worker/test_chat_activity_events.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/worker/handlers.py projects/server/src/interactors/worker/subscription_runner.py projects/server/tests/interactors/worker/test_chat_activity_events.py
git commit -m "feat: persist agent activity events from chat handlers"
```

---

### Task 8: API — activity list + SSE stream endpoints

**Files:**
- Create: `projects/server/src/interactors/api/routes/activity.py`
- Modify: `projects/server/src/interactors/api/routes/__init__.py` (register the router)
- Modify: `projects/server/src/interactors/api/schemas.py` (add `ActivityEventOut`)
- Test: `projects/server/tests/api/test_activity_stream.py`

**Interfaces:**
- Consumes: `AgentEventRepository.list_after` (Task 3); the existing SSE helpers/constants (`_SSE_POLL_SECONDS`, `_SSE_MAX_SECONDS`, `EventSourceResponse`) — copy the pattern from `routes/runs.py`.
- Produces:
  - `ActivityEventOut(BaseModel)` with `seq: int`, `kind: str`, `payload: dict`, `createdAt: datetime` (alias `created_at`).
  - `GET /threads/{id}/activity?after=` and `GET /runs/{id}/activity?after=` → `Envelope[list[ActivityEventOut]]` (replay).
  - `GET /threads/{id}/activity/stream` and `GET /runs/{id}/activity/stream` → `EventSourceResponse`.
  - Internal `stream_agent_events(session_factory, owner_id, scope, after)` async generator backing both stream routes.

- [ ] **Step 1: Write the failing test**

```python
# projects/server/tests/api/test_activity_stream.py
from domain.agent.events import EVENT_STATUS, EVENT_TEXT, AgentEvent


def _seed(client_uow):
    with client_uow.transaction() as uow:
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:w1", kind=EVENT_STATUS))
        uow.agent_events.create(AgentEvent(owner_id="", scope="thread:w1",
                                           kind=EVENT_TEXT, payload={"text": "hello"}))


def test_activity_replay_returns_events_after_seq(client, client_uow):
    _seed(client_uow)
    resp = client.get("/threads/w1/activity?after=1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [e["seq"] for e in data] == [2]
    assert data[0]["kind"] == "text_block"
    assert data[0]["payload"] == {"text": "hello"}


def test_activity_replay_empty_when_none(client):
    resp = client.get("/threads/nope/activity?after=0")
    assert resp.status_code == 200
    assert resp.json()["data"] == []
```

(Use the same `client` / `client_uow` fixtures the other API tests use, e.g. from `tests/api/conftest.py`. If a `client_uow` fixture does not exist, seed via the existing app-scoped UoW fixture used by `tests/api/test_runs_sse.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_activity_stream.py -v`
Expected: FAIL with 404 (route not registered)

- [ ] **Step 3a: Add the schema**

In `projects/server/src/interactors/api/schemas.py`:
```python
class ActivityEventOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    seq: int
    kind: str
    payload: dict = Field(default_factory=dict)
    createdAt: datetime = Field(alias="created_at")
```
(Match the import style already used in that file for `BaseModel`, `Field`, `ConfigDict`, `datetime`.)

- [ ] **Step 3b: Add the router**

```python
# projects/server/src/interactors/api/routes/activity.py
import asyncio
import time

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from adapters.database.uow import SqlUnitOfWork
from domain.agent.events import EVENT_ERROR, EVENT_FINAL, stream_scope
from interactors.api.deps import get_owner_id, get_uow
from interactors.api.envelope import Envelope, ok
from interactors.api.schemas import ActivityEventOut

router = APIRouter(tags=["activity"])

_POLL_SECONDS = 0.3
_MAX_SECONDS = 60 * 30


def _out(ev) -> ActivityEventOut:
    return ActivityEventOut(seq=ev.seq, kind=ev.kind, payload=ev.payload, created_at=ev.created_at)


def _replay(uow: SqlUnitOfWork, scope: str, after: int):
    # limit=0 → read_multi returns all rows (its `if page_size > 0` guard skips the limit)
    return ok([_out(e) for e in uow.agent_events.list_after(scope, after, limit=0)])


@router.get("/threads/{id}/activity", response_model=Envelope[list[ActivityEventOut]])
def thread_activity(id: str, after: int = 0, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    return _replay(uow, stream_scope(thread_id=id), after)


@router.get("/runs/{id}/activity", response_model=Envelope[list[ActivityEventOut]])
def run_activity(id: str, after: int = 0, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    return _replay(uow, stream_scope(run_id=id), after)


def _stream(request: Request, owner_id: str, scope: str, after: int) -> EventSourceResponse:
    async def gen():
        cursor = after
        deadline = time.monotonic() + _MAX_SECONDS
        while time.monotonic() < deadline:
            uow = SqlUnitOfWork(request.app.state.session_factory,
                                required_filters={"owner_id": owner_id})
            with uow.transaction():
                rows = uow.agent_events.list_after(scope, cursor, limit=200)
            for ev in rows:
                cursor = ev.seq
                yield {"data": _out(ev).model_dump_json()}
                if ev.kind in (EVENT_FINAL, EVENT_ERROR):
                    return
            await asyncio.sleep(_POLL_SECONDS)

    return EventSourceResponse(gen())


@router.get("/threads/{id}/activity/stream")
def thread_activity_stream(id: str, request: Request, after: int = 0,
                           owner_id: str = Depends(get_owner_id)):  # noqa: B008
    return _stream(request, owner_id, stream_scope(thread_id=id), after)


@router.get("/runs/{id}/activity/stream")
def run_activity_stream(id: str, request: Request, after: int = 0,
                        owner_id: str = Depends(get_owner_id)):  # noqa: B008
    return _stream(request, owner_id, stream_scope(run_id=id), after)
```

(Confirm `list_after` accepts `limit`; the replay passes a large limit for full history. If `page_size=0` means "all" in `read_multi`, pass `limit=0` instead of `1000` — check `SqlRepository.read_multi` and match the convention used by `routes/runs.py`.)

Register it in `projects/server/src/interactors/api/routes/__init__.py`:
```python
from interactors.api.routes.activity import router as activity_router
...
    app.include_router(activity_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/server && uv run pytest tests/api/test_activity_stream.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/routes/activity.py projects/server/src/interactors/api/routes/__init__.py projects/server/src/interactors/api/schemas.py projects/server/tests/api/test_activity_stream.py
git commit -m "feat: activity replay + SSE stream endpoints"
```

- [ ] **Step 6: Backend gate checkpoint**

Run: `cd /Users/noel/projects/naaf/.worktrees/stream-agent-output && make lint && make coverage`
Expected: lint clean; coverage ≥ 80%; all tests pass. Fix any fallout before Phase 3.

---

## Phase 3 — UI

### Task 9: OpenAPI contract + `useAgentActivity` hook + mocks

**Files:**
- Modify: `projects/ui/openapi/naaf-api.yaml` (add the two `…/activity` paths + `ActivityEventOut` schema)
- Regenerate: `projects/ui/src/lib/api/schema.d.ts` (via `pnpm gen:api`)
- Modify: `projects/ui/src/lib/api/queryKeys.ts` (add `threadActivity`, `runActivity`)
- Create: `projects/ui/src/lib/api/hooks/useAgentActivity.ts`
- Modify: `projects/ui/src/lib/api/hooks/index.ts` (export it, if hooks are barrel-exported)
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts` (mock `GET …/activity`)
- Test: `projects/ui/src/lib/api/hooks/useAgentActivity.test.tsx`

**Interfaces:**
- Consumes: `useEventSource`, `apiList`, `queryKeys`, generated `components["schemas"]["ActivityEventOut"]`.
- Produces:
  - `type ActivityEvent = components["schemas"]["ActivityEventOut"]`.
  - `reduceActivity(events: ActivityEvent[]): { isWorking: boolean; textBlocks: string[]; toolCalls: {name:string; result?:string}[]; error?: string; done: boolean }` (pure — unit-testable, mirrors `mergeEventsBySeq`'s exported-pure-helper style).
  - `useAgentActivity(scope: {threadId?: string; runId?: string} | null): { events: ActivityEvent[] } & ReturnType<typeof reduceActivity>`.

- [ ] **Step 1: Add the OpenAPI paths + schema, regenerate types**

In `projects/ui/openapi/naaf-api.yaml`, add an `ActivityEventOut` schema under `components.schemas`:
```yaml
    ActivityEventOut:
      type: object
      required: [seq, kind, payload, createdAt]
      properties:
        seq: { type: integer }
        kind: { type: string }
        payload: { type: object, additionalProperties: true }
        createdAt: { type: string, format: date-time }
```
Add the replay path (the stream path is consumed via `EventSource`, not typed, so it is optional in the spec) — model it on the existing `/runs/{id}/events` envelope-list path already in the file:
```yaml
  /threads/{id}/activity:
    get:
      parameters:
        - { name: id, in: path, required: true, schema: { type: string } }
        - { name: after, in: query, required: false, schema: { type: integer, default: 0 } }
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items: { $ref: "#/components/schemas/ActivityEventOut" }
```
Then regenerate:
```bash
cd projects/ui && pnpm gen:api
```
Expected: `src/lib/api/schema.d.ts` now contains `ActivityEventOut`.

- [ ] **Step 2: Write the failing test**

```tsx
// projects/ui/src/lib/api/hooks/useAgentActivity.test.tsx
import { describe, expect, it } from "vitest";
import { reduceActivity } from "./useAgentActivity";

describe("reduceActivity", () => {
  it("marks working after a status event with no content yet", () => {
    const s = reduceActivity([{ seq: 1, kind: "status", payload: { state: "working" }, createdAt: "" }]);
    expect(s.isWorking).toBe(true);
    expect(s.textBlocks).toEqual([]);
    expect(s.done).toBe(false);
  });

  it("collects text blocks and tool calls in order", () => {
    const s = reduceActivity([
      { seq: 1, kind: "status", payload: {}, createdAt: "" },
      { seq: 2, kind: "text_block", payload: { text: "Hi" }, createdAt: "" },
      { seq: 3, kind: "tool_call", payload: { name: "list_board" }, createdAt: "" },
    ]);
    expect(s.textBlocks).toEqual(["Hi"]);
    expect(s.toolCalls).toEqual([{ name: "list_board" }]);
  });

  it("clears working and marks done on final", () => {
    const s = reduceActivity([
      { seq: 1, kind: "status", payload: {}, createdAt: "" },
      { seq: 2, kind: "final", payload: { text: "done" }, createdAt: "" },
    ]);
    expect(s.isWorking).toBe(false);
    expect(s.done).toBe(true);
  });

  it("surfaces error kind", () => {
    const s = reduceActivity([{ seq: 1, kind: "error", payload: { message: "boom" }, createdAt: "" }]);
    expect(s.error).toBe("boom");
    expect(s.done).toBe(true);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/lib/api/hooks/useAgentActivity.test.tsx`
Expected: FAIL — module `./useAgentActivity` not found.

- [ ] **Step 4: Write the hook**

```tsx
// projects/ui/src/lib/api/hooks/useAgentActivity.ts
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import { useEventSource } from "../../hooks/useEventSource";
import type { components } from "../schema";

export type ActivityEvent = components["schemas"]["ActivityEventOut"];

export interface ActivityState {
  isWorking: boolean;
  textBlocks: string[];
  toolCalls: { name: string; result?: string }[];
  error?: string;
  done: boolean;
}

export function reduceActivity(events: ActivityEvent[]): ActivityState {
  const textBlocks: string[] = [];
  const toolCalls: { name: string; result?: string }[] = [];
  let error: string | undefined;
  let done = false;
  let sawStatus = false;
  for (const ev of events) {
    const p = (ev.payload ?? {}) as Record<string, unknown>;
    if (ev.kind === "status") sawStatus = true;
    else if (ev.kind === "text_block") textBlocks.push(String(p.text ?? ""));
    else if (ev.kind === "tool_call") toolCalls.push({ name: String(p.name ?? "") });
    else if (ev.kind === "tool_result" && toolCalls.length)
      toolCalls[toolCalls.length - 1].result = String(p.result ?? "");
    else if (ev.kind === "final") done = true;
    else if (ev.kind === "error") { error = String(p.message ?? "error"); done = true; }
  }
  const isWorking = (sawStatus || textBlocks.length > 0 || toolCalls.length > 0) && !done;
  return { isWorking, textBlocks, toolCalls, error, done };
}

function scopePath(scope: { threadId?: string; runId?: string }): string {
  return scope.threadId ? `/threads/${scope.threadId}` : `/runs/${scope.runId}`;
}

export function useAgentActivity(scope: { threadId?: string; runId?: string } | null) {
  const base = scope ? scopePath(scope) : null;
  const key = scope?.threadId
    ? queryKeys.threadActivity(scope.threadId)
    : queryKeys.runActivity(scope?.runId);

  const history = useQuery({
    queryKey: key,
    queryFn: () => apiList<ActivityEvent>(`${base}/activity`),
    enabled: Boolean(base),
    select: (page) => page.results,
  });

  const [streamed, setStreamed] = useState<ActivityEvent[]>([]);
  useEffect(() => { setStreamed([]); }, [base]);

  const hist = history.data ?? [];
  const lastSeq = hist.length ? hist[hist.length - 1].seq : 0;
  useEventSource<ActivityEvent>(
    base ? `/api${base}/activity/stream?after=${lastSeq}` : null,
    (ev) => setStreamed((prev) => [...prev, ev]),
  );

  const bySeq = new Map<number, ActivityEvent>();
  for (const e of [...hist, ...streamed]) bySeq.set(e.seq, e);
  const events = Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq);
  return { events, ...reduceActivity(events) };
}
```

Add to `queryKeys.ts`:
```typescript
  threadActivity: (id?: string) => ["threads", id ?? "none", "activity"] as const,
  runActivity: (id?: string) => ["runs", id ?? "none", "activity"] as const,
```

Add a mock handler in `mocks/handlers.ts` (return an empty envelope list so mocked UI runs without a backend):
```typescript
  http.get("*/threads/:id/activity", () => envelope([])),
  http.get("*/runs/:id/activity", () => envelope([])),
```
(Use the existing `envelope`/`ok` mock helper already in that file; match its list-envelope shape.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd projects/ui && pnpm vitest run src/lib/api/hooks/useAgentActivity.test.tsx`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add projects/ui/openapi/naaf-api.yaml projects/ui/src/lib/api/schema.d.ts projects/ui/src/lib/api/queryKeys.ts projects/ui/src/lib/api/hooks/useAgentActivity.ts projects/ui/src/lib/api/hooks/index.ts projects/ui/src/lib/api/mocks/handlers.ts projects/ui/src/lib/api/hooks/useAgentActivity.test.tsx
git commit -m "feat: useAgentActivity hook + activity contract + mocks"
```

---

### Task 10: `ActivityFeed` + wire into the chat `Thread`

**Files:**
- Create: `projects/ui/src/components/thread/ActivityFeed.tsx`
- Modify: `projects/ui/src/components/thread/Thread.tsx` (render the feed + drive `showTyping` from live activity)
- Test: `projects/ui/src/components/thread/ActivityFeed.test.tsx`

**Interfaces:**
- Consumes: `useAgentActivity` + `reduceActivity` result (Task 9), existing `TypingIndicator` / `TypingRow`.
- Produces: `ActivityFeed({ threadId }: { threadId: string })` — renders the live trace (streamed text blocks + `🔧 <tool> → <result>` lines) while a turn is in flight; renders nothing once `done` and no in-flight state (the settled `Message` row carries the final text).

- [ ] **Step 1: Write the failing test**

```tsx
// projects/ui/src/components/thread/ActivityFeed.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActivityFeed } from "./ActivityFeed";
import * as hook from "../../lib/api/hooks/useAgentActivity";

describe("ActivityFeed", () => {
  it("shows typing indicator while working with no content", () => {
    vi.spyOn(hook, "useAgentActivity").mockReturnValue({
      events: [], isWorking: true, textBlocks: [], toolCalls: [], done: false,
    } as never);
    render(<ActivityFeed threadId="w1" />);
    expect(screen.getByTestId("activity-typing")).toBeInTheDocument();
  });

  it("renders streamed text and tool lines", () => {
    vi.spyOn(hook, "useAgentActivity").mockReturnValue({
      events: [], isWorking: true, textBlocks: ["Planning…"],
      toolCalls: [{ name: "create_task", result: "ok" }], done: false,
    } as never);
    render(<ActivityFeed threadId="w1" />);
    expect(screen.getByText("Planning…")).toBeInTheDocument();
    expect(screen.getByText(/create_task/)).toBeInTheDocument();
  });

  it("renders nothing when idle/done", () => {
    vi.spyOn(hook, "useAgentActivity").mockReturnValue({
      events: [], isWorking: false, textBlocks: [], toolCalls: [], done: true,
    } as never);
    const { container } = render(<ActivityFeed threadId="w1" />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/components/thread/ActivityFeed.test.tsx`
Expected: FAIL — `./ActivityFeed` not found.

- [ ] **Step 3: Write the component + wire `Thread`**

```tsx
// projects/ui/src/components/thread/ActivityFeed.tsx
import { useAgentActivity } from "../../lib/api/hooks/useAgentActivity";
import { TypingIndicator } from "../ui/TypingIndicator";

export function ActivityFeed({ threadId }: { threadId: string }) {
  const { isWorking, textBlocks, toolCalls } = useAgentActivity({ threadId });
  if (!isWorking) return null;
  const hasContent = textBlocks.length > 0 || toolCalls.length > 0;
  return (
    <div className="flex gap-2.5 items-start mb-3.5" data-testid="activity-feed">
      <div className="w-[26px] h-[26px] flex-none" />
      <div className="flex flex-col gap-1 px-3.5 py-2.5"
        style={{ background: "#131618", border: "1px solid rgba(255,255,255,0.07)", borderRadius: "3px 10px 10px 10px" }}>
        {textBlocks.map((t, i) => (
          <p key={`t${i}`} className="text-[12px] text-[#c4c5cb] whitespace-pre-wrap">{t}</p>
        ))}
        {toolCalls.map((c, i) => (
          <p key={`c${i}`} className="font-mono text-[10px] text-[#7c6cf0]">
            🔧 {c.name}{c.result ? ` → ${c.result.slice(0, 40)}` : "…"}
          </p>
        ))}
        {!hasContent && <div data-testid="activity-typing"><TypingIndicator /></div>}
      </div>
    </div>
  );
}
```

In `Thread.tsx`: import `ActivityFeed`, and replace the `{showTyping && <TypingRow />}` line with the live feed (the feed subsumes the typing indicator):
```tsx
            <ActivityFeed threadId={workItemId} />
```
Remove the now-unused `showTyping` prop usage and `TypingRow`/`TypingIndicator` import if nothing else references them (check `Thread.test.tsx` — update any assertion that relied on `showTyping`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm vitest run src/components/thread/ActivityFeed.test.tsx src/components/thread/Thread.test.tsx`
Expected: PASS (ActivityFeed 3 passed; Thread green after any assertion update).

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/components/thread/ActivityFeed.tsx projects/ui/src/components/thread/Thread.tsx projects/ui/src/components/thread/ActivityFeed.test.tsx projects/ui/src/components/thread/Thread.test.tsx
git commit -m "feat: live ActivityFeed + typing indicator in chat thread"
```

---

### Task 11: Wire the run monitor to `useAgentActivity`

**Files:**
- Modify: `projects/ui/src/modules/detail/AgentMonitor.tsx` (the run monitor — it already calls `useRun(`)
- Test: `projects/ui/src/modules/detail/AgentMonitor.test.tsx` (extend the existing suite)

**Interfaces:**
- Consumes: `useAgentActivity({ runId })`, the `ActivityFeed` component from Task 10 (extended to accept a `scope`).
- Produces: the active stage renders the same live trace (streamed text + tool lines) beneath the stage list.

- [ ] **Step 1: Read the run monitor**

Read `projects/ui/src/modules/detail/AgentMonitor.tsx` to find where it renders `useRun` events/stages, and where the active run id is available — that is where the run-scoped feed goes.

- [ ] **Step 2: Write the failing test**

Add to `projects/ui/src/modules/detail/AgentMonitor.test.tsx` (mirror Task 10's `vi.spyOn(hook, "useAgentActivity")` approach) asserting the streamed text appears while the run is active:
```tsx
it("renders live agent activity for the active run", () => {
  vi.spyOn(activityHook, "useAgentActivity").mockReturnValue({
    events: [], isWorking: true, textBlocks: ["Implementing…"], toolCalls: [], done: false,
  } as never);
  // ...render the monitor with a running run id...
  expect(screen.getByText("Implementing…")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/modules/detail/AgentMonitor.test.tsx`
Expected: FAIL — no live activity element yet.

- [ ] **Step 4: Add the feed to the monitor**

Render a run-scoped feed near the active stage, reusing the same presentation as `ActivityFeed` but with `useAgentActivity({ runId })`. If the presentation is identical, extract `ActivityFeed` to accept `scope: {threadId?: string; runId?: string}` instead of `threadId` and pass `{ runId }` here (update Task 10's call site to `<ActivityFeed scope={{ threadId: workItemId }} />` and the tests accordingly). Keep it DRY — one `ActivityFeed`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd projects/ui && pnpm vitest run src/modules/detail/AgentMonitor.test.tsx src/components/thread/ActivityFeed.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit + full UI gate**

```bash
git add -A
git commit -m "feat: live agent activity in the run monitor"
cd /Users/noel/projects/naaf/.worktrees/stream-agent-output && (cd projects/ui && pnpm test) && make lint && make coverage
```
Expected: all UI tests pass; lint clean; coverage ≥ 80%.

---

## Final verification (before PR)

- [ ] `make lint` — ruff + mypy clean.
- [ ] `make coverage` — ≥ 80%, all backend tests pass.
- [ ] `cd projects/ui && pnpm test` — all vitest suites pass.
- [ ] Manual live check (subscription path): `make dev NAAF_AGENT_RUNTIME=claude_code`, open a project chat, send a message → within ~1s a `…` indicator appears, then tool-call lines (`list_board`, `create_task`, …) and text stream in, then the turn settles into the final message. Reload mid-turn → the coarse trace replays.
- [ ] Push + open PR: `git push -u origin feat/stream-agent-output` then `gh pr create` (focused title, summary, test plan).

## Self-review notes (addressed)

- **Spec coverage:** adapter streaming (T4/T5), `agent_events` persist-coarse (T1–T3), worker sink incl. `status`→content→`final` and the typing indicator (T7/T10), chat + runs surfaces (T10/T11), poll-based SSE reusing the runs pattern (T8), reconciliation via the settled `Message` row (T10 renders `ActivityFeed` alongside `useThreadMessages`), error handling (streaming runner error/timeout in T4; `error` event surfaced in T7 via the `finally`/`EVENT_ERROR` path and reduced in T9), migration number `0014` (T2).
- **Deferred (out of scope, per spec):** Redis token-delta channel; token-level replay; cost rendering from payloads.
- **Type consistency:** `emit(kind, payload)` (`EventSink`) is used identically across T4/T5/T6/T7; `stream_scope` keys (`thread:`/`run:`) match between T1, T7, T8, T9; `ActivityEventOut` fields (`seq/kind/payload/createdAt`) match between T8 schema, T9 YAML, and the hook.
