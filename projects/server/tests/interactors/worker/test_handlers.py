"""Unit tests for the worker agent handlers — focused on the advance loop."""

import uuid
from dataclasses import dataclass, field

from adapters.agent.runtime.fake import FakeAgentRuntime
from domain.agent.runtime import StageResult
from domain.errors import RecordNotFound
from domain.project import Project
from domain.runs.events import EventType
from domain.runs.messages import AgentMessage, MessageType
from domain.runs.run import Run, RunStatus, Stage
from domain.work_item import WorkItem, WorkItemKind
from interactors.worker import handlers

# ---------------------------------------------------------------------------
# Minimal fakes for the unit test — no DB, no bus infra needed
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


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


def test_advance_full_auto_chains_provision_stub_then_hands_off_to_engineer():
    """full_auto: PLAN passed -> PROVISION stub (inline) -> IMPLEMENT handoff to engineer.

    Proves:
    - advance chains through the PROVISION stub stage without stopping
    - advance publishes a RUN_STAGE message to the engineer at IMPLEMENT
    - the saved run's current_stage is IMPLEMENT after the call
    """
    # Arrange
    run = Run(
        owner_id="u",
        work_item_id="w",
        project_id="p",
        autonomy_level="full_auto",
        status=RunStatus.RUNNING,
        current_stage=Stage.PLAN,
    )
    ctx, runs, bus = _make_ctx()
    runs.create(run)

    # Act — simulate lead advancing after PLAN passed
    handlers.advance(ctx, run, StageResult(passed=True))

    # Assert: bus received exactly one message, destined for the engineer
    assert len(bus.published) == 1, f"Expected 1 bus message, got {len(bus.published)}"
    msg = bus.published[0]
    assert isinstance(msg, AgentMessage)
    assert msg.role == "engineer"
    assert msg.type is MessageType.RUN_STAGE
    assert msg.payload.get("stage") == Stage.IMPLEMENT.value

    # Assert: run was updated to IMPLEMENT stage
    saved_run = runs.read(run.id)
    assert saved_run.current_stage is Stage.IMPLEMENT


def _start_msg(run_id: str) -> AgentMessage:
    return AgentMessage(
        owner_id="u",
        run_id=run_id,
        recipient="lead",
        role="lead",
        type=MessageType.START,
    )


def test_start_emits_provision_stage_before_plan_stage():
    """handle_lead START must emit STAGE_STARTED for PROVISION before PLAN.

    ctx.projects is None → _provision returns a skip (passed=True), so the full
    pipeline runs. We verify ordering by inspecting the stage on each STAGE_STARTED event.
    """
    run = Run(owner_id="u", work_item_id="w", project_id="p", autonomy_level="full_auto")
    ctx, runs, _ = _make_ctx()
    runs.create(run)

    handlers.handle_lead(_start_msg(run.id), ctx)

    started = [
        e for e in ctx.run_events.saved.values()
        if e.type is EventType.STAGE_STARTED
    ]
    stage_order = [e.stage.value for e in started]
    assert stage_order[0] == "provision", f"expected provision first, got {stage_order}"
    assert stage_order[1] == "plan", f"expected plan second, got {stage_order}"


def test_start_with_failing_provision_halts_before_plan():
    """When PROVISION fails, the run must end FAILED and PLAN must never start.

    We trigger a failing provision by wiring ctx.projects to return a project
    whose repo_path points at a non-existent directory, causing provision_workspace
    to raise (git clone fails) so _provision returns passed=False.
    """
    run = Run(owner_id="u", work_item_id="w", project_id="p", autonomy_level="full_auto")
    ctx, runs, _ = _make_ctx()
    runs.create(run)

    # Wire work_items so _provision can look up the project
    wi = WorkItem(id="w", owner_id="u", project_id="p", kind=WorkItemKind.TASK,
                  title="T", status="todo")
    ctx.work_items.create(wi)

    # Wire projects with a bad repo path so provision_workspace raises
    bad_repo = f"/tmp/naaf-nonexistent-{uuid.uuid4().hex}"
    project = Project(id="p", owner_id="u", name="P", repo_path=bad_repo)
    ctx.projects = FakeRepo()
    ctx.projects.create(project)

    handlers.handle_lead(_start_msg(run.id), ctx)

    # Run must be FAILED
    saved_run = runs.read(run.id)
    assert saved_run.status is RunStatus.FAILED, (
        f"expected FAILED after provision error, got {saved_run.status}"
    )

    # PLAN must never have started
    started_stages = {
        e.stage.value
        for e in ctx.run_events.saved.values()
        if e.type is EventType.STAGE_STARTED
    }
    assert "plan" not in started_stages, (
        f"PLAN must not start when PROVISION fails; started stages: {started_stages}"
    )
