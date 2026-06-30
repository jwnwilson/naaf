from dataclasses import dataclass
from typing import Any

from domain.agent.runtime import AgentRuntime, StageResult
from domain.base import utcnow
from domain.errors import RecordNotFound
from domain.runs.coupling import work_item_status_for
from domain.runs.events import EventType, RunEvent
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.pipeline import Finish, GateStep, Retry, next_step
from domain.runs.run import Gate, Run, RunStatus, Stage
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus

_STUB_STAGES = {Stage.PROVISION, Stage.PR, Stage.LEARN}


@dataclass
class HandlerContext:
    runs: Any
    run_events: Any
    work_items: Any
    bus: Any
    session: Any
    runtime: AgentRuntime


def emit(ctx: HandlerContext, run: Run, type_: EventType, *, stage: Stage | None = None,
         role: str | None = None, payload: dict | None = None) -> None:
    """Publish a RunEvent; owner_id is left blank — the repo stamps it from required_filters."""
    ctx.run_events.create(RunEvent(
        owner_id="",
        run_id=run.id,
        type=type_,
        stage=stage,
        role=role,
        payload=payload or {},
    ))


def couple(ctx: HandlerContext, run: Run) -> None:
    """Sync the work item status to match the run's current state."""
    target_value = work_item_status_for(run)
    if target_value is None:
        return
    try:
        wi = ctx.work_items.read(run.work_item_id)
    except RecordNotFound:
        return
    target = WorkItemStatus(target_value)
    if wi.status == target:
        return
    new_status = validate_transition(wi.status, target)
    ctx.work_items.update(wi.id, wi.model_copy(update={"status": new_status}))


def _save(ctx: HandlerContext, run: Run) -> Run:
    ctx.runs.update(run.id, run)
    return run


def _run_stage_inline(ctx: HandlerContext, run: Run, role: str, stage: Stage) -> StageResult:
    run = _save(ctx, run.model_copy(update={"current_stage": stage}))
    emit(ctx, run, EventType.STAGE_STARTED, stage=stage, role=role)
    outcome = ctx.runtime.run_stage(role, stage, {"verify_attempts": run.verify_attempts})
    for ev in outcome.events:
        emit(ctx, run, EventType.LOG, stage=stage, role=role, payload={"message": ev.message})
    event_type = EventType.STAGE_PASSED if outcome.result.passed else EventType.STAGE_FAILED
    emit(ctx, run, event_type, stage=stage, role=role, payload={"summary": outcome.result.summary})
    return outcome.result


def advance(ctx: HandlerContext, run: Run, result: StageResult) -> None:
    """Lead's control loop: act on next_step until a handoff, gate, or finish."""
    while True:
        step = next_step(run, result)

        if isinstance(step, Finish):
            run = _save(ctx, run.model_copy(update={"status": step.status, "ended_at": utcnow()}))
            emit(ctx, run, EventType.RUN_FINISHED, payload={"status": step.status.value})
            couple(ctx, run)
            return

        if isinstance(step, GateStep):
            assert run.current_stage is not None
            gate = Gate(kind=step.kind, stage=run.current_stage)
            run = _save(ctx, run.model_copy(update={
                "status": RunStatus.AWAITING_GATE,
                "pending_gate": gate,
            }))
            emit(ctx, run, EventType.GATE_REQUESTED, role="lead",
                 payload={"kind": step.kind.value})
            couple(ctx, run)
            return

        if isinstance(step, Retry):
            run = _save(ctx, run.model_copy(update={
                "verify_attempts": run.verify_attempts + 1,
                "current_stage": Stage.IMPLEMENT,
            }))
            _handoff(ctx, run, "engineer", Stage.IMPLEMENT)
            return

        # Advance to a specific stage
        stage = step.stage
        if stage is Stage.IMPLEMENT:
            run = _save(ctx, run.model_copy(update={"current_stage": stage}))
            _handoff(ctx, run, "engineer", stage)
            return

        if stage is Stage.VERIFY:
            run = _save(ctx, run.model_copy(update={"current_stage": stage}))
            _handoff(ctx, run, "qa", stage)
            return

        # Stub stages (PROVISION, PR, LEARN): run inline then keep looping
        if stage in _STUB_STAGES:
            result = _run_stage_inline(ctx, run, "lead", stage)
            run = ctx.runs.read(run.id)
            continue

        raise ValueError(f"unexpected advance stage: {stage}")


def _handoff(ctx: HandlerContext, run: Run, role: str, stage: Stage) -> None:
    ctx.bus.publish(
        AgentMessage(
            owner_id=run.owner_id,
            run_id=run.id,
            recipient=recipient_key(run.id, role),
            role=role,
            type=MessageType.RUN_STAGE,
            payload={"stage": stage.value},
        ),
        ctx.session,
    )


def handle_lead(msg: AgentMessage, ctx: HandlerContext) -> None:
    run = ctx.runs.read(msg.run_id)

    if msg.type is MessageType.START:
        run = _save(ctx, run.model_copy(update={
            "status": RunStatus.RUNNING, "started_at": utcnow()
        }))
        emit(ctx, run, EventType.RUN_STARTED, role="lead")
        couple(ctx, run)
        result = _run_stage_inline(ctx, run, "lead", Stage.PLAN)
        run = ctx.runs.read(run.id)
        advance(ctx, run, result)

    elif msg.type is MessageType.STAGE_REPORT:
        result = StageResult(
            passed=bool(msg.payload.get("passed")),
            summary=msg.payload.get("summary", ""),
        )
        advance(ctx, run, result)

    elif msg.type is MessageType.GATE_RESOLVED:
        if msg.payload.get("decision") == "approve":
            kind = run.pending_gate.kind
            run = _save(ctx, run.model_copy(update={
                "status": RunStatus.RUNNING,
                "pending_gate": None,
                "resolved_gates": [*run.resolved_gates, kind],
            }))
            emit(ctx, run, EventType.GATE_RESOLVED, role="lead",
                 payload={"decision": "approve"})
            advance(ctx, run, StageResult(passed=True))
        else:
            run = _save(ctx, run.model_copy(update={
                "status": RunStatus.CANCELLED,
                "pending_gate": None,
                "ended_at": utcnow(),
            }))
            emit(ctx, run, EventType.GATE_RESOLVED, role="lead",
                 payload={"decision": "reject"})
            emit(ctx, run, EventType.RUN_FINISHED, payload={"status": "cancelled"})
            couple(ctx, run)


def handle_engineer(msg: AgentMessage, ctx: HandlerContext) -> None:
    if msg.type is not MessageType.RUN_STAGE:
        return
    run = ctx.runs.read(msg.run_id)
    result = _run_stage_inline(ctx, run, "engineer", Stage.IMPLEMENT)
    _report(ctx, run, result)


def handle_qa(msg: AgentMessage, ctx: HandlerContext) -> None:
    if msg.type is not MessageType.RUN_STAGE:
        return
    run = ctx.runs.read(msg.run_id)
    result = _run_stage_inline(ctx, run, "qa", Stage.VERIFY)
    _report(ctx, run, result)


def _report(ctx: HandlerContext, run: Run, result: StageResult) -> None:
    ctx.bus.publish(
        AgentMessage(
            owner_id=run.owner_id,
            run_id=run.id,
            recipient=recipient_key(run.id, "lead"),
            role="lead",
            type=MessageType.STAGE_REPORT,
            payload={"passed": result.passed, "summary": result.summary},
        ),
        ctx.session,
    )


_HANDLERS = {"lead": handle_lead, "engineer": handle_engineer, "qa": handle_qa}


def dispatch(msg: AgentMessage, ctx: HandlerContext) -> None:
    handler = _HANDLERS.get(msg.role)
    if handler is None:
        raise ValueError(f"unknown role: {msg.role!r}")
    handler(msg, ctx)
