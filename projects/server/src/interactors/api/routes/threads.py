from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.messaging.message import AuthorKind, Message
from domain.messaging.thread import thread_from_run
from fastapi import APIRouter, Depends

from interactors.api.contract import MessageCreate, MessageOut, ThreadOut, iso
from interactors.api.deps import get_uow

router = APIRouter(prefix="/threads", tags=["threads"])


def _thread_out(view) -> ThreadOut:
    return ThreadOut(
        id=view.id,
        agentId=view.agent_id,
        workItemId=view.work_item_id,
        createdAt=iso(view.created_at),
    )


def _message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        conversationId=m.thread_id,
        role=m.author_kind.value,
        agentId=None,  # TODO: align with new agent model
        content=m.content,
        createdAt=iso(m.created_at),
    )


def _page_meta(page) -> dict:
    return {
        "total": page.total,
        "page_size": page.page_size,
        "page_number": page.page_number,
    }


@router.get("", response_model=Envelope[list[ThreadOut]])
def list_threads(
    page_size: int = 50,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    page = uow.runs.read_multi(
        page_size=page_size, page_number=page_number, order_by="-created_at"
    )
    return ok(
        [_thread_out(thread_from_run(r)) for r in page.results],
        meta=_page_meta(page),
    )


@router.get("/{id}/messages", response_model=Envelope[list[MessageOut]])
def list_messages(
    id: UUID,
    page_size: int = 50,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    uow.runs.read(id.hex)  # 404 if the run/thread is not the caller's
    page = uow.messages.read_multi(
        filters={"thread_id": id.hex},
        page_size=page_size,
        page_number=page_number,
        order_by="created_at",
    )
    return ok([_message_out(m) for m in page.results], meta=_page_meta(page))


@router.post("/{id}/messages", status_code=201, response_model=Envelope[MessageOut])
def post_message(
    id: UUID,
    payload: MessageCreate,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    uow.runs.read(id.hex)  # 404 if the run/thread is not the caller's
    created = uow.messages.create(
        Message(
            owner_id="",
            thread_id=id.hex,
            author_kind=AuthorKind.USER,
            content=payload.content,
        )
    )
    return ok(_message_out(created))
