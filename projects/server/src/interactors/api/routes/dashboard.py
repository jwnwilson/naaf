from datetime import UTC, datetime, timedelta

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.dashboard import build_token_series, to_activity_event
from fastapi import APIRouter, Depends

from interactors.api.contract import ActivityEventOut, TokenPointOut, iso
from interactors.api.deps import get_uow

router = APIRouter(tags=["dashboard"])

TOKEN_WINDOW_DAYS = 7
ACTIVITY_LIMIT = 20
_ACTIVITY_SCAN = 40  # read extra so dropping `log`s still fills the list


@router.get("/dashboard/token-usage", response_model=Envelope[list[TokenPointOut]])
def token_usage(uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    now = datetime.now(UTC)
    cutoff = (now - timedelta(days=TOKEN_WINDOW_DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    events = uow.run_events.read_multi(
        filters={"created_at__gte": cutoff}, page_size=1000
    ).results
    series = build_token_series(events, now.date(), TOKEN_WINDOW_DAYS)
    return ok([TokenPointOut(day=p.day, tokens=p.tokens) for p in series])


@router.get("/activity", response_model=Envelope[list[ActivityEventOut]])
def activity(uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    events = uow.run_events.read_multi(
        order_by="-global_seq", page_size=_ACTIVITY_SCAN
    ).results
    items = [it for it in (to_activity_event(e) for e in events) if it is not None]
    items = items[:ACTIVITY_LIMIT]
    return ok([
        ActivityEventOut(
            id=it.id, type=it.type, description=it.description,
            agentId=it.agent_id, workItemId=it.work_item_id,
            createdAt=iso(it.created_at),
        )
        for it in items
    ])
