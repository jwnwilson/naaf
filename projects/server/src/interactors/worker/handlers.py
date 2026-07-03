import re
from dataclasses import dataclass, field
from typing import Any

from adapters.agent.provision import provision_workspace
from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.runtime import AgentEvent, AgentRuntime, StageOutcome, StageResult
from domain.base import utcnow
from domain.errors import RecordNotFound
from domain.messaging.chat import ChatTurn
from domain.messaging.dispatch import plan_fanout
from domain.messaging.message import AuthorKind, Message, MessageKind
from domain.messaging.question import question_payload, resolve_payload
from domain.runs.coupling import work_item_status_for
from domain.runs.events import EventType, RunEvent
from domain.runs.messages import AgentMessage, MessageType, chat_recipient, recipient_key
from domain.runs.pipeline import Finish, GateStep, Retry, next_step
from domain.runs.run import Gate, Run, RunStatus, Stage, StageState, StageStatus
from domain.team import AgentDefinition, AgentRole
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus

_STUB_STAGES = {Stage.PROVISION, Stage.PR, Stage.LEARN}

_PR_URL_RE = re.compile(r"https://github\.com/\S+?/pull/\d+")


@dataclass
class HandlerContext:
    runs: Any
    run_events: Any
    work_items: Any
    notifications: Any  # NotificationRepository | None — None in dead-letter cleanup
    bus: Any
    runtime: AgentRuntime | None  # None only in dead-letter cleanup (couple path — no stage runs)
    workspace_root: str = ""
    role_aliases: dict[str, str] | None = field(default=None)
    projects: Any = None
    messages: Any = None  # MessageRepository | None — None in dead-letter cleanup
    chat_responder: Any = None  # ChatResponder | None — None in dead-letter cleanup


_ROLE_MAP = {
    "lead": AgentRole.LEAD,
    "architect": AgentRole.ARCHITECT,
    "engineer": AgentRole.BACKEND,
    "backend": AgentRole.BACKEND,
    "frontend": AgentRole.FRONTEND,
    "qa": AgentRole.QA,
    "devops": AgentRole.DEVOPS,
}


def build_stage_context(ctx: HandlerContext, run: Run, role: str, stage: Stage) -> StageContext:
    try:
        wi = ctx.work_items.read(run.work_item_id)
        brief = WorkItemBrief(
            title=getattr(wi, "title", ""),
            body=getattr(wi, "body", ""),
            acceptance_criteria=[
                ac.text for ac in (getattr(wi, "acceptance_criteria", None) or [])
            ],
        )
    except RecordNotFound:
        brief = WorkItemBrief(title="")
    aliases = ctx.role_aliases or {}
    agent = AgentDefinition(
        owner_id=run.owner_id,
        team_id="",
        role=_ROLE_MAP.get(role, AgentRole.CUSTOM),
        model_alias=aliases.get(role, ""),
    )
    root = ctx.workspace_root or "/tmp/naaf-workspaces"
    return StageContext(
        run_id=run.id,
        role=role,
        stage=stage,
        workspace_path=f"{root}/{run.id}",
        work_item=brief,
        agent=agent,
        verify_attempts=run.verify_attempts,
    )


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


def _work_item_title(ctx: HandlerContext, run: Run) -> str:
    try:
        wi = ctx.work_items.read(run.work_item_id)
        return getattr(wi, "title", "") or run.work_item_id
    except RecordNotFound:
        return run.work_item_id


def narrate(
    ctx: HandlerContext,
    run: Run,
    *,
    role: str,
    content: str,
    kind: MessageKind = MessageKind.TEXT,
    payload: dict | None = None,
) -> None:
    """Post a human-readable message into the run's work-item thread.

    Additive to RunEvents; no-ops on the dead-letter path where messages is None.
    """
    if ctx.messages is None:
        return
    ctx.messages.create(Message(
        owner_id="",  # stamped from required_filters
        thread_id=run.work_item_id,
        author_kind=AuthorKind.AGENT,
        author_role=role,
        kind=kind,
        content=content,
        payload=payload or {},
        run_id=run.id,
    ))


def _resolve_question(ctx: HandlerContext, run: Run, option: str) -> None:
    """Mark the run's latest unresolved question message with the chosen option."""
    if ctx.messages is None:
        return
    rows = ctx.messages.read_multi(
        filters={"thread_id": run.work_item_id}, order_by="created_at"
    ).results
    for m in reversed(rows):
        if (
            m.kind.value == "question"
            and m.payload.get("run_id") == run.id
            and m.payload.get("resolved_option") is None
        ):
            ctx.messages.update(
                m.id, m.model_copy(update={"payload": resolve_payload(m.payload, option)})
            )
            return


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


def _start_stage(ctx: HandlerContext, run: Run, role: str, stage: Stage) -> Run:
    new_entry = StageState(stage=stage, status=StageStatus.RUNNING, role=role, started_at=utcnow())
    run = _save(ctx, run.model_copy(update={
        "current_stage": stage,
        "stages": [*run.stages, new_entry],
    }))
    emit(ctx, run, EventType.STAGE_STARTED, stage=stage, role=role)
    return run


def _finish_stage(
    ctx: HandlerContext, run: Run, role: str, stage: Stage, outcome: StageOutcome
) -> StageResult:
    for ev in outcome.events:
        emit(ctx, run, EventType.LOG, stage=stage, role=role, payload={"message": ev.message})
    final_status = StageStatus.PASSED if outcome.result.passed else StageStatus.FAILED
    updated_entry = run.stages[-1].model_copy(update={"status": final_status, "ended_at": utcnow()})
    _save(ctx, run.model_copy(update={
        "stages": [*run.stages[:-1], updated_entry],
        "token_usage": run.token_usage + outcome.result.tokens,
    }))
    event_type = EventType.STAGE_PASSED if outcome.result.passed else EventType.STAGE_FAILED
    emit(ctx, run, event_type, stage=stage, role=role,
         payload={"summary": outcome.result.summary, "tokens": outcome.result.tokens})
    verdict = "passed" if outcome.result.passed else "failed"
    summary = outcome.result.summary or "(no summary)"
    narrate(ctx, run, role=role, content=f"{stage.value} {verdict}: {summary}")
    return outcome.result


def _run_stage_inline(ctx: HandlerContext, run: Run, role: str, stage: Stage) -> StageResult:
    run = _start_stage(ctx, run, role, stage)
    assert ctx.runtime is not None, "_run_stage_inline requires a non-None runtime"
    outcome = ctx.runtime.run_stage(role, stage, build_stage_context(ctx, run, role, stage))
    return _finish_stage(ctx, run, role, stage, outcome)


def _provision(ctx: HandlerContext, run: Run) -> StageOutcome:
    def skip(msg: str) -> StageOutcome:
        return StageOutcome(
            events=[AgentEvent(message=msg)],
            result=StageResult(passed=True, summary=msg),
        )

    if ctx.projects is None:
        return skip("provision skipped (no project repository configured)")
    try:
        wi = ctx.work_items.read(run.work_item_id)
        project = ctx.projects.read(wi.project_id)
    except RecordNotFound:
        return skip("provision skipped (project not found)")
    repo = project.repo_url or project.repo_path
    if not repo:
        return skip("provision skipped (project has no repo)")
    root = ctx.workspace_root or "/tmp/naaf-workspaces"
    try:
        path = provision_workspace(repo, run.id, root)
    except Exception as exc:  # git failures should fail the stage, not crash the worker
        return StageOutcome(
            events=[AgentEvent(message=f"provision failed: {exc}")],
            result=StageResult(passed=False, summary=f"provision failed: {exc}"),
        )
    return StageOutcome(
        events=[
            AgentEvent(message=f"cloned {repo}"),
            AgentEvent(message=f"branch agent/{run.id} at {path}"),
        ],
        result=StageResult(passed=True, summary=f"provisioned {path}"),
    )


def _capture_pr_url(ctx: HandlerContext, run: Run, result: StageResult) -> None:
    match = _PR_URL_RE.search(result.summary or "")
    if not match:
        return
    url = match.group(0)
    run = ctx.runs.read(run.id)
    emit(ctx, run, EventType.LOG, stage=Stage.PR, role="lead",
         payload={"message": f"PR opened: {url}", "pr_url": url})


def _run_provision_inline(ctx: HandlerContext, run: Run) -> StageResult:
    run = _start_stage(ctx, run, "lead", Stage.PROVISION)
    return _finish_stage(ctx, run, "lead", Stage.PROVISION, _provision(ctx, run))


def advance(ctx: HandlerContext, run: Run, result: StageResult) -> None:
    """Lead's control loop: act on next_step until a handoff, gate, or finish."""
    while True:
        step = next_step(run, result)

        if isinstance(step, Finish):
            run = _save(ctx, run.model_copy(update={"status": step.status, "ended_at": utcnow()}))
            emit(ctx, run, EventType.RUN_FINISHED, payload={"status": step.status.value})
            narrate(ctx, run, role="lead", content=f"Run finished: {step.status.value}.")
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
            narrate(
                ctx, run, role="lead",
                kind=MessageKind.QUESTION,
                content=f"{step.kind.value.capitalize()} gate — review and approve to continue.",
                payload=question_payload(run.id, step.kind.value),
            )
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
            if stage is Stage.PROVISION:
                # unreachable: PROVISION runs once at START, never advanced-to; kept for safety
                result = _run_provision_inline(ctx, run)
            elif stage is Stage.PR:
                result = _run_stage_inline(ctx, run, "lead", stage)
                _capture_pr_url(ctx, run, result)
            else:  # LEARN
                result = _run_stage_inline(ctx, run, "curator", stage)
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
    )


def handle_lead(msg: AgentMessage, ctx: HandlerContext) -> None:
    run = ctx.runs.read(msg.run_id)

    if msg.type is MessageType.START:
        run = _save(ctx, run.model_copy(update={
            "status": RunStatus.RUNNING, "started_at": utcnow()
        }))
        emit(ctx, run, EventType.RUN_STARTED, role="lead")
        narrate(ctx, run, role="lead",
                content=f"Starting work on \"{_work_item_title(ctx, run)}\". Planning now.")
        couple(ctx, run)
        prov = _run_provision_inline(ctx, run)
        run = ctx.runs.read(run.id)
        if not prov.passed:
            advance(ctx, run, prov)  # I1: failed PROVISION halts the run (Finish FAILED)
            return
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
        if run.pending_gate is None:  # duplicate message — gate already resolved; ack and drop
            return
        if msg.payload.get("decision") == "approve":
            kind = run.pending_gate.kind
            run = _save(ctx, run.model_copy(update={
                "status": RunStatus.RUNNING,
                "pending_gate": None,
                "resolved_gates": [*run.resolved_gates, kind],
            }))
            emit(ctx, run, EventType.GATE_RESOLVED, role="lead",
                 payload={"decision": "approve"})
            _resolve_question(ctx, run, "approve")
            narrate(ctx, run, role="lead",
                    content="Gate approved — continuing.")
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
            _resolve_question(ctx, run, "reject")
            narrate(ctx, run, role="lead",
                    content="Gate rejected — stopping.")
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
    )


_HANDLERS = {"lead": handle_lead, "engineer": handle_engineer, "qa": handle_qa}


def _work_item_title_by_id(ctx: HandlerContext, work_item_id: str) -> str:
    """Return the work-item title (or its id as fallback) without requiring a Run."""
    try:
        wi = ctx.work_items.read(work_item_id)
        return getattr(wi, "title", "") or work_item_id
    except RecordNotFound:
        return work_item_id


def _post_agent_message(
    ctx: HandlerContext, work_item_id: str, role: str, content: str
) -> None:
    """Persist a plain TEXT message from a role-agent into the thread (no run)."""
    if ctx.messages is None:
        return
    ctx.messages.create(Message(
        owner_id="",  # stamped from required_filters on the live path
        thread_id=work_item_id,
        author_kind=AuthorKind.AGENT,
        author_role=role,
        kind=MessageKind.TEXT,
        content=content,
        run_id=None,
    ))


def _publish_chat(
    ctx: HandlerContext, work_item_id: str, owner_id: str, role: str, depth: int
) -> None:
    """Publish a CHAT bus message directed at ``role`` in the given work-item thread."""
    ctx.bus.publish(AgentMessage(
        owner_id=owner_id,
        run_id="",
        recipient=chat_recipient(work_item_id, role),
        role=role,
        type=MessageType.CHAT,
        payload={"work_item_id": work_item_id, "depth": depth},
    ))


def handle_chat(msg: AgentMessage, ctx: HandlerContext) -> None:
    """Handle an agent-chat message: respond in the thread and fan out @mentions.

    Fan-out uses plan_fanout (EXPLICIT mentions only — an agent reply that
    mentions no one addresses no one, so it must not default to lead). The depth
    guard in plan_fanout terminates agent->agent chains at MAX_FANOUT_DEPTH hops.
    """
    if ctx.chat_responder is None or ctx.messages is None:
        return

    work_item_id: str = msg.payload["work_item_id"]
    depth: int = msg.payload.get("depth", 0)
    role: str = msg.role

    # Build the conversation history for the responder
    history_rows = ctx.messages.read_multi(
        filters={"thread_id": work_item_id}, order_by="created_at"
    ).results
    history = [
        ChatTurn(role=(m.author_role or "user"), content=m.content)
        for m in history_rows
    ]

    title = _work_item_title_by_id(ctx, work_item_id)
    reply_text = ctx.chat_responder.respond(role, history, title)

    if not reply_text.strip():
        return

    _post_agent_message(ctx, work_item_id, role, reply_text)

    for target in plan_fanout(reply_text, depth + 1):
        _publish_chat(ctx, work_item_id, msg.owner_id, target, depth + 1)


def dispatch(msg: AgentMessage, ctx: HandlerContext) -> None:
    if msg.type is MessageType.CHAT:
        handle_chat(msg, ctx)
        return
    handler = _HANDLERS.get(msg.role)
    if handler is None:
        raise ValueError(f"unknown role: {msg.role!r}")
    handler(msg, ctx)
