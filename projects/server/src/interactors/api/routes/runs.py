"""Run API routes: start, list, get, events, gate."""
import asyncio
import time
from uuid import UUID

from adapters.bus.ports import MessageBus
from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.errors import InvalidTransition
from domain.runs.events import EventType, RunEvent
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run, StageState
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from interactors.api.auth import get_owner_id
from interactors.api.contract import (
    GateDecisionIn,
    GateOut,
    RunEventOut,
    RunOut,
    StageStateOut,
    iso,
)
from interactors.api.deps import get_bus, get_uow

_SSE_POLL_SECONDS = 0.25
_SSE_MAX_SECONDS = 600

COST_PER_1K_TOKENS = 0.003  # flat placeholder; real per-model pricing is A5

# /runs collection endpoints (owner-unscoped path, still owner-filtered by UoW)
router = APIRouter(prefix="/runs", tags=["runs"])
# /work-items/{id}/runs nested endpoint
work_items_router = APIRouter(tags=["runs"])


def _stage_out(s: StageState) -> StageStateOut:
    return StageStateOut(
        stage=s.stage.value,
        status=s.status.value,
        role=s.role,
        startedAt=s.started_at.isoformat() if s.started_at else None,
        endedAt=s.ended_at.isoformat() if s.ended_at else None,
    )


def _run_out(run: Run) -> RunOut:
    pending = run.pending_gate
    gate_out: GateOut | None = None
    if pending is not None:
        gate_out = GateOut(kind=pending.kind.value, stage=pending.stage.value)
    return RunOut(
        id=run.id,
        workItemId=run.work_item_id,
        projectId=run.project_id,
        autonomyLevel=run.autonomy_level,
        status=run.status.value,
        currentStage=run.current_stage.value if run.current_stage else None,
        stages=[_stage_out(s) for s in run.stages],
        pendingGate=gate_out,
        createdAt=iso(run.created_at),
        updatedAt=iso(run.updated_at),
        startedAt=run.started_at.isoformat() if run.started_at else None,
        endedAt=run.ended_at.isoformat() if run.ended_at else None,
        tokenUsage=run.token_usage,
        cost=round(run.token_usage / 1000 * COST_PER_1K_TOKENS, 4),
        prUrl=run.pr_url,
    )


def _run_event_out(e: RunEvent) -> RunEventOut:
    stage = e.stage.value if e.stage is not None else None
    return RunEventOut(
        id=e.id,
        runId=e.run_id,
        seq=e.seq,
        stage=stage,
        role=e.role,
        type=e.type.value,
        payload=e.payload,
        createdAt=iso(e.created_at),
    )


@work_items_router.post(
    "/work-items/{id}/runs",
    status_code=201,
    response_model=Envelope[RunOut],
)
def start_run(
    id: UUID,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    owner_id: str = Depends(get_owner_id),  # noqa: B008
    bus: MessageBus = Depends(get_bus),  # noqa: B008
):
    """Start an agent run for a work item.

    Creates a queued Run, enqueues a START message on the bus (atomic with the
    transaction), and transitions the work item to in_progress.
    """
    work_item = uow.work_items.read(id.hex)
    project = uow.projects.read(work_item.project_id)

    # Validate the transition before creating the run so any bad state is 409
    new_status = validate_transition(work_item.status, WorkItemStatus.IN_PROGRESS)

    run = uow.runs.create(Run(
        owner_id="",  # stamped by repo from required_filters
        work_item_id=work_item.id,
        project_id=project.id,
        autonomy_level=project.autonomy_level.value,
    ))

    bus.publish(AgentMessage(
        owner_id=owner_id,
        run_id=run.id,
        recipient=recipient_key(run.id, "lead"),
        role="lead",
        type=MessageType.START,
    ))

    uow.work_items.update(
        work_item.id, work_item.model_copy(update={"status": new_status})
    )

    return ok(_run_out(run))


@router.get("", response_model=Envelope[list[RunOut]])
def list_runs(
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    work_item: str | None = None,
    project: str | None = None,
    status: str | None = None,
    page_size: int = 50,
    page_number: int = 1,
):
    filters: dict[str, str] = {}
    if work_item:
        filters["work_item_id"] = work_item
    if project:
        filters["project_id"] = project
    if status:
        filters["status"] = status
    page = uow.runs.read_multi(filters=filters, page_size=page_size, page_number=page_number)
    return ok(
        [_run_out(r) for r in page.results],
        meta={
            "total": page.total,
            "page_size": page.page_size,
            "page_number": page.page_number,
        },
    )


@router.get("/{id}", response_model=Envelope[RunOut])
def get_run(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    return ok(_run_out(uow.runs.read(id.hex)))


@router.get("/{id}/events", response_model=Envelope[list[RunEventOut]])
def list_run_events(
    id: UUID,
    after: int = 0,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    """Return events for a run with seq > after (default 0 = all events)."""
    uow.runs.read(id.hex)  # owner-scoped 404 if run not found
    page = uow.run_events.read_multi(
        filters={"run_id": id.hex, "seq__gt": after},
        page_size=0,
        order_by="seq",
    )
    return ok([_run_event_out(e) for e in page.results])


@router.get("/{id}/events/stream")
def stream_run_events(
    id: UUID,
    request: Request,
    after: int = 0,
    owner_id: str = Depends(get_owner_id),  # noqa: B008
) -> EventSourceResponse:
    """Stream run events as SSE.

    Polls run_events with seq > after on a short interval, yielding each row as
    a data: JSON line (RunEventOut shape). Closes after emitting a run_finished
    event or after _SSE_MAX_SECONDS. Does NOT hold a long-lived DB transaction —
    a fresh SqlUnitOfWork is opened and closed on every poll iteration.
    """

    # Upfront owner-scoped lookup: raises RecordNotFound -> 404 if missing/foreign
    uow = SqlUnitOfWork(
        request.app.state.session_factory,
        required_filters={"owner_id": owner_id},
    )
    with uow.transaction():
        uow.runs.read(id.hex)

    async def gen():
        cursor = after
        deadline = time.monotonic() + _SSE_MAX_SECONDS
        while time.monotonic() < deadline:
            uow = SqlUnitOfWork(
                request.app.state.session_factory,
                required_filters={"owner_id": owner_id},
            )
            with uow.transaction():
                rows = uow.run_events.read_multi(
                    filters={"run_id": id.hex, "seq__gt": cursor},
                    order_by="seq",
                    page_size=0,
                ).results

            for ev in rows:
                cursor = ev.seq
                yield {"data": _run_event_out(ev).model_dump_json()}
                if ev.type == EventType.RUN_FINISHED:
                    return
            await asyncio.sleep(_SSE_POLL_SECONDS)

    return EventSourceResponse(gen())


@router.post("/{id}/gate", response_model=Envelope[RunOut])
def resolve_gate(
    id: UUID,
    body: GateDecisionIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    owner_id: str = Depends(get_owner_id),  # noqa: B008
    bus: MessageBus = Depends(get_bus),  # noqa: B008
):
    """Submit a gate decision (approve/reject) for a run awaiting human review.

    Returns 409 if the run has no pending gate — the caller should poll GET
    /runs/{id} first to confirm a gate is waiting.
    """
    run = uow.runs.read(id.hex)
    if run.pending_gate is None:
        raise InvalidTransition("no pending gate to resolve")
    bus.publish(AgentMessage(
        owner_id=owner_id,
        run_id=run.id,
        recipient=recipient_key(run.id, "lead"),
        role="lead",
        type=MessageType.GATE_RESOLVED,
        payload={"decision": body.decision},
    ))
    return ok(_run_out(run))
