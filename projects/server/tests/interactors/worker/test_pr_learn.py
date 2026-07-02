"""Tests for PR URL capture and LEARN-as-curator routing."""

from dataclasses import dataclass, field

from adapters.agent.runtime.fake import FakeAgentRuntime
from domain.agent.runtime import StageResult
from domain.errors import RecordNotFound
from domain.runs.events import EventType
from domain.runs.messages import AgentMessage, MessageType
from domain.runs.run import Run, RunStatus, Stage
from interactors.worker import handlers
from interactors.worker.handlers import _capture_pr_url

# ---------------------------------------------------------------------------
# Minimal fakes (same pattern as test_handlers.py)
# ---------------------------------------------------------------------------


@dataclass
class FakeBus:
    published: list = field(default_factory=list)

    def publish(self, msg) -> None:
        self.published.append(msg)


class FakeRepo:
    """In-memory store keyed by entity .id."""

    def __init__(self) -> None:
        self.saved: dict = {}

    def create(self, dto):
        self.saved[dto.id] = dto
        return dto

    def update(self, id_, dto):
        self.saved[id_] = dto
        return dto

    def read(self, id_):
        try:
            return self.saved[id_]
        except KeyError:
            raise RecordNotFound(id_) from None


def _make_ctx(*, fail_verify_times: int = 0) -> tuple[handlers.HandlerContext, FakeRepo, FakeBus]:
    runs = FakeRepo()
    run_events = FakeRepo()
    work_items = FakeRepo()
    bus = FakeBus()
    runtime = FakeAgentRuntime(fail_verify_times=fail_verify_times)
    ctx = handlers.HandlerContext(
        runs=runs,
        run_events=run_events,
        work_items=work_items,
        notifications=None,
        bus=bus,
        runtime=runtime,
    )
    return ctx, runs, bus


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_capture_pr_url_emits_event_with_url():
    """_capture_pr_url emits a LOG RunEvent with pr_url when the summary has a GitHub PR URL."""
    # Arrange
    ctx, runs, _bus = _make_ctx()
    run = Run(owner_id="u", work_item_id="w", project_id="p", autonomy_level="full_auto",
              status=RunStatus.RUNNING, current_stage=Stage.PR)
    runs.create(run)
    result = StageResult(passed=True, summary="Done. https://github.com/acme/app/pull/42")

    # Act
    _capture_pr_url(ctx, run, result)

    # Assert
    created_events = list(ctx.run_events.saved.values())
    assert len(created_events) == 1, f"Expected 1 event, got {len(created_events)}"
    ev = created_events[0]
    assert ev.type is EventType.LOG
    assert ev.stage is Stage.PR
    assert ev.role == "lead"
    assert ev.payload["pr_url"] == "https://github.com/acme/app/pull/42"
    assert "PR opened" in ev.payload["message"]


def test_capture_pr_url_noop_without_url():
    """_capture_pr_url emits no event when the summary contains no GitHub PR URL."""
    # Arrange
    ctx, runs, _bus = _make_ctx()
    run = Run(owner_id="u", work_item_id="w", project_id="p", autonomy_level="full_auto",
              status=RunStatus.RUNNING, current_stage=Stage.PR)
    runs.create(run)
    result = StageResult(passed=True, summary="no url here")

    # Act
    _capture_pr_url(ctx, run, result)

    # Assert
    assert len(ctx.run_events.saved) == 0, "Expected no events when summary has no PR URL"


def test_learn_runs_as_curator():
    """LEARN stage is dispatched with role='curator'; PR stage still uses role='lead'.

    Drives a full_auto run to completion via advance() with FakeAgentRuntime and
    inspects STAGE_STARTED events to confirm per-stage role assignment.
    """
    # Arrange
    ctx, runs, _bus = _make_ctx()
    run = Run(
        owner_id="u",
        work_item_id="w",
        project_id="p",
        autonomy_level="full_auto",
        status=RunStatus.RUNNING,
        current_stage=Stage.PLAN,
    )
    runs.create(run)

    # Act — send a START message to handle_lead which runs PLAN then advances through
    # PROVISION → IMPLEMENT (handoff) → (report back) → VERIFY (handoff) → (report back)
    # → PR → LEARN → FINISH
    msg = AgentMessage(
        owner_id="u",
        run_id=run.id,
        recipient=f"{run.id}:lead",
        role="lead",
        type=MessageType.START,
    )
    handlers.handle_lead(msg, ctx)

    # The lead hands off IMPLEMENT to engineer; simulate engineer reporting back passed
    engineer_result_msg = AgentMessage(
        owner_id="u",
        run_id=run.id,
        recipient=f"{run.id}:lead",
        role="lead",
        type=MessageType.STAGE_REPORT,
        payload={"passed": True, "summary": "implemented"},
    )
    handlers.handle_lead(engineer_result_msg, ctx)

    # Lead hands off VERIFY to QA; simulate QA reporting back passed
    qa_result_msg = AgentMessage(
        owner_id="u",
        run_id=run.id,
        recipient=f"{run.id}:lead",
        role="lead",
        type=MessageType.STAGE_REPORT,
        payload={"passed": True, "summary": "verified"},
    )
    handlers.handle_lead(qa_result_msg, ctx)

    # Assert: collect all STAGE_STARTED events and check roles
    all_events = list(ctx.run_events.saved.values())
    stage_started = {
        ev.stage: ev.role
        for ev in all_events
        if ev.type is EventType.STAGE_STARTED and ev.stage is not None
    }

    assert Stage.LEARN in stage_started, (
        f"No STAGE_STARTED event found for LEARN. Events: {[e.type for e in all_events]}"
    )
    assert stage_started[Stage.LEARN] == "curator", (
        f"LEARN stage expected role='curator', got {stage_started[Stage.LEARN]!r}"
    )

    assert Stage.PR in stage_started, "No STAGE_STARTED event found for PR"
    assert stage_started[Stage.PR] == "lead", (
        f"PR stage expected role='lead', got {stage_started[Stage.PR]!r}"
    )
