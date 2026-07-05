"""Activity event replay and SSE stream routes."""
import asyncio
import time

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.agent.events import EVENT_ERROR, EVENT_FINAL, stream_scope
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from interactors.api.auth import get_owner_id
from interactors.api.contract import ActivityEventOut, iso
from interactors.api.deps import get_uow

router = APIRouter(tags=["activity"])

_POLL_SECONDS = 0.3
_MAX_SECONDS = 60 * 30


def _out(ev) -> ActivityEventOut:
    return ActivityEventOut(
        seq=ev.seq,
        kind=ev.kind,
        payload=ev.payload,
        createdAt=iso(ev.created_at),
    )


def _replay(uow: SqlUnitOfWork, scope: str, after: int):
    # limit=0 → read_multi skips the LIMIT clause (page_size=0 guard in read_multi)
    return ok([_out(e) for e in uow.agent_events.list_after(scope, after, limit=0)])


@router.get("/threads/{id}/activity", response_model=Envelope[list[ActivityEventOut]])
def thread_activity(
    id: str,
    after: int = 0,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    return _replay(uow, stream_scope(thread_id=id), after)


@router.get("/runs/{id}/activity", response_model=Envelope[list[ActivityEventOut]])
def run_activity(
    id: str,
    after: int = 0,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    return _replay(uow, stream_scope(run_id=id), after)


def _stream(request: Request, owner_id: str, scope: str, after: int) -> EventSourceResponse:
    async def gen():
        cursor = after
        deadline = time.monotonic() + _MAX_SECONDS
        while time.monotonic() < deadline:
            uow = SqlUnitOfWork(
                request.app.state.session_factory,
                required_filters={"owner_id": owner_id},
            )
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
def thread_activity_stream(
    id: str,
    request: Request,
    after: int = 0,
    owner_id: str = Depends(get_owner_id),  # noqa: B008
):
    return _stream(request, owner_id, stream_scope(thread_id=id), after)


@router.get("/runs/{id}/activity/stream")
def run_activity_stream(
    id: str,
    request: Request,
    after: int = 0,
    owner_id: str = Depends(get_owner_id),  # noqa: B008
):
    return _stream(request, owner_id, stream_scope(run_id=id), after)
