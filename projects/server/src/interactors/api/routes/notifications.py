from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from fastapi import APIRouter, Depends

from interactors.api.contract import NotificationOut, iso
from interactors.api.deps import get_uow

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _notification_out(n) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        runId=n.run_id,
        workItemId=n.work_item_id,
        type=n.type,
        title=n.title,
        body=n.body,
        read=n.read,
        createdAt=iso(n.created_at),
        updatedAt=iso(n.updated_at),
    )


@router.get("", response_model=Envelope[list[NotificationOut]])
def list_notifications(
    read: bool | None = None,
    page_size: int = 50,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    filters: dict = {}
    if read is not None:
        filters["read"] = read
    page = uow.notifications.read_multi(
        filters=filters, page_size=page_size, page_number=page_number
    )
    return ok(
        [_notification_out(n) for n in page.results],
        meta={
            "total": page.total,
            "page_size": page.page_size,
            "page_number": page.page_number,
        },
    )


@router.post("/{id}/read", response_model=Envelope[NotificationOut])
def mark_notification_read(
    id: UUID,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    n = uow.notifications.read(id.hex)
    updated = uow.notifications.update(id.hex, n.model_copy(update={"read": True}))
    return ok(_notification_out(updated))
