"""Integration tests for run-stage activity events emitted by _run_stage_inline.

Design contract: _run_stage_inline builds an event sink scoped to the run,
calls runtime.set_event_sink() so the runtime can forward streamed events,
emits EVENT_STATUS before and EVENT_FINAL after run_stage(), and clears the
sink in a finally block. All events commit in their own transactions so a
fresh UoW sees them immediately.
"""
import pytest
from adapters.database.uow import SqlUnitOfWork
from domain.agent.context import StageContext
from domain.agent.events import EVENT_ERROR, EVENT_FINAL, EVENT_STATUS, stream_scope
from domain.agent.runtime import AgentEvent, StageOutcome, StageResult
from domain.errors import RecordNotFound
from domain.runs.run import Run, RunStatus, Stage
from interactors.worker.handlers import HandlerContext, _run_stage_inline

# ---------------------------------------------------------------------------
# Fake collaborators
# ---------------------------------------------------------------------------


class _CapturingRuntime:
    """Runtime that records the injected sink, calls it with a text_block,
    then returns a successful StageOutcome."""

    def __init__(self):
        self._sink = None
        self.sink_calls: list[tuple] = []

    def set_event_sink(self, emit) -> None:
        self._sink = emit

    def run_stage(self, role: str, stage: Stage, ctx: StageContext) -> StageOutcome:
        if self._sink:
            self._sink("text_block", {"text": "working on it"})
        return StageOutcome(
            events=[AgentEvent(message="done")],
            result=StageResult(passed=True, summary="ok", tokens=100),
        )


class _RaisingRuntime:
    """Runtime that raises during run_stage to exercise the error path."""

    def __init__(self, exc: Exception):
        self._exc = exc
        self._sink = None

    def set_event_sink(self, emit) -> None:
        self._sink = emit

    def run_stage(self, role: str, stage: Stage, ctx: StageContext) -> StageOutcome:
        raise self._exc


class _FakeRepo:
    """Minimal in-memory stand-in for runs / run_events / work_items / etc."""

    def __init__(self, items=None):
        self._items = {item.id: item for item in (items or [])}
        self.updated: list = []
        self.created: list = []

    def read(self, id_):
        try:
            return self._items[id_]
        except KeyError as exc:
            raise RecordNotFound(id_) from exc

    def update(self, id_, obj):
        self._items[id_] = obj
        self.updated.append(obj)
        return obj

    def create(self, obj):
        self.created.append(obj)
        return obj


def _make_run(owner_id: str) -> Run:
    return Run(
        id="a" * 32,
        owner_id=owner_id,
        work_item_id="wi-" + "b" * 28,
        project_id="proj-" + "c" * 27,
        autonomy_level="full_auto",
        status=RunStatus.RUNNING,
    )


# ---------------------------------------------------------------------------
# Test 1 — happy path: status + final emitted and visible via fresh UoW
# ---------------------------------------------------------------------------


def test_run_stage_inline_emits_status_and_final(session_factory):
    """_run_stage_inline must emit EVENT_STATUS before run_stage() and
    EVENT_FINAL after, each committed in its own transaction."""
    owner_id = "u-run-1"
    run = _make_run(owner_id)
    scope = stream_scope(run_id=run.id)

    runs_repo = _FakeRepo([run])
    run_events_repo = _FakeRepo()
    work_items_repo = _FakeRepo()

    ctx = HandlerContext(
        runs=runs_repo,
        run_events=run_events_repo,
        work_items=work_items_repo,
        notifications=None,
        bus=None,
        runtime=_CapturingRuntime(),
        session_factory=session_factory,
    )

    result = _run_stage_inline(ctx, run, "lead", Stage.PLAN)

    assert result.passed, "stage should have passed"

    # A fresh UoW must see both the status and final events
    reader = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner_id})
    with reader.transaction():
        events = reader.agent_events.list_after(scope, 0)

    kinds = [e.kind for e in events]
    assert EVENT_STATUS in kinds, f"status event missing; got {kinds}"
    assert EVENT_FINAL in kinds, f"final event missing; got {kinds}"

    # STATUS must come before FINAL
    status_idx = kinds.index(EVENT_STATUS)
    final_idx = kinds.index(EVENT_FINAL)
    assert status_idx < final_idx, "status must precede final"

    # The status payload carries stage and role
    status_ev = next(e for e in events if e.kind == EVENT_STATUS)
    assert status_ev.payload.get("stage") == Stage.PLAN.value
    assert status_ev.payload.get("role") == "lead"


# ---------------------------------------------------------------------------
# Test 2 — error path: EVENT_ERROR committed even when run_stage raises
# ---------------------------------------------------------------------------


def test_run_stage_inline_emits_error_when_runtime_raises(session_factory):
    """When runtime.run_stage() raises, an EVENT_ERROR is committed and the
    exception propagates. No EVENT_FINAL should appear."""
    owner_id = "u-run-2"
    run = _make_run(owner_id)
    scope = stream_scope(run_id=run.id)

    runs_repo = _FakeRepo([run])
    run_events_repo = _FakeRepo()
    work_items_repo = _FakeRepo()

    ctx = HandlerContext(
        runs=runs_repo,
        run_events=run_events_repo,
        work_items=work_items_repo,
        notifications=None,
        bus=None,
        runtime=_RaisingRuntime(RuntimeError("stage exploded")),
        session_factory=session_factory,
    )

    with pytest.raises(RuntimeError, match="stage exploded"):
        _run_stage_inline(ctx, run, "engineer", Stage.IMPLEMENT)

    reader = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner_id})
    with reader.transaction():
        events = reader.agent_events.list_after(scope, 0)

    kinds = [e.kind for e in events]
    assert EVENT_ERROR in kinds, f"error event missing; got {kinds}"
    assert EVENT_FINAL not in kinds, f"final must not appear on error path; got {kinds}"

    error_ev = next(e for e in events if e.kind == EVENT_ERROR)
    assert "stage exploded" in error_ev.payload.get("message", "")
