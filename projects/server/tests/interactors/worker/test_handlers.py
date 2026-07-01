"""Unit tests for the worker agent handlers — focused on the advance loop."""

from dataclasses import dataclass, field

from adapters.agent.runtime.fake import FakeAgentRuntime
from domain.agent.runtime import StageResult
from domain.runs.messages import AgentMessage, MessageType
from domain.runs.run import Run, RunStatus, Stage
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
        return self.saved[id_]


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
