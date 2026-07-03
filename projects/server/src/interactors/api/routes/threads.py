from adapters.bus.ports import MessageBus
from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.errors import RecordNotFound
from domain.messaging.mentions import parse_mentions
from domain.messaging.message import AuthorKind, Message, MessageKind
from domain.messaging.question import is_valid_option
from domain.messaging.thread import ThreadView, thread_from_work_item
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from fastapi import APIRouter, Depends, HTTPException

from interactors.api.auth import get_owner_id
from interactors.api.contract import (
    AnswerIn,
    MessageCreate,
    MessageOut,
    ThreadDetailOut,
    ThreadOut,
    iso,
)
from interactors.api.deps import get_bus, get_uow

router = APIRouter(prefix="/threads", tags=["threads"])


def _thread_out(view: ThreadView) -> ThreadOut:
    return ThreadOut(
        id=view.id,
        workItemId=view.work_item_id,
        title=view.title,
        status=view.status,
        lastMessage=view.last_message,
        messageCount=view.message_count,
        participants=view.participants,
        createdAt=iso(view.created_at),
    )


def _message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        threadId=m.thread_id,
        authorKind=m.author_kind.value,
        authorRole=m.author_role,
        model=m.model_alias,
        kind=m.kind.value,
        content=m.content,
        mentions=m.mentions,
        payload=m.payload,
        runId=m.run_id,
        createdAt=iso(m.created_at),
    )


def _page_meta(page) -> dict:
    return {"total": page.total, "page_size": page.page_size, "page_number": page.page_number}


def _read_item_or_404(uow: SqlUnitOfWork, wid: str):
    try:
        return uow.work_items.read(wid)
    except RecordNotFound as exc:
        raise HTTPException(status_code=404, detail="thread not found") from exc


def _messages_for(uow: SqlUnitOfWork, wid: str) -> list[Message]:
    page = uow.messages.read_multi(
        filters={"thread_id": wid}, page_size=500, page_number=1, order_by="created_at"
    )
    return page.results


def _files_written(messages: list[Message]) -> list[dict]:
    return [
        m.payload for m in messages
        if m.kind is MessageKind.FILE_WRITE and m.payload.get("path")
    ]


@router.get("", response_model=Envelope[list[ThreadOut]])
def list_threads(
    page_size: int = 50,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    page = uow.work_items.read_multi(
        page_size=page_size, page_number=page_number, order_by="-updated_at"
    )
    threads = [
        _thread_out(thread_from_work_item(item, _messages_for(uow, item.id)))
        for item in page.results
    ]
    return ok(threads, meta=_page_meta(page))


@router.get("/{id}", response_model=Envelope[ThreadDetailOut])
def get_thread(id: str, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    item = _read_item_or_404(uow, id)
    messages = _messages_for(uow, id)
    base = _thread_out(thread_from_work_item(item, messages))
    detail = ThreadDetailOut(**base.model_dump(), filesWritten=_files_written(messages))
    return ok(detail)


@router.get("/{id}/messages", response_model=Envelope[list[MessageOut]])
def list_messages(
    id: str,
    page_size: int = 500,
    page_number: int = 1,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    _read_item_or_404(uow, id)
    page = uow.messages.read_multi(
        filters={"thread_id": id}, page_size=page_size, page_number=page_number,
        order_by="created_at",
    )
    return ok([_message_out(m) for m in page.results], meta=_page_meta(page))


@router.post("/{id}/messages", status_code=201, response_model=Envelope[MessageOut])
def post_message(
    id: str,
    payload: MessageCreate,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    _read_item_or_404(uow, id)
    created = uow.messages.create(Message(
        owner_id="",
        thread_id=id,
        author_kind=AuthorKind.USER,
        kind=MessageKind.TEXT,
        content=payload.content,
        mentions=parse_mentions(payload.content),
    ))
    return ok(_message_out(created))


@router.post("/{id}/messages/{msg_id}/answer", response_model=Envelope[MessageOut])
def answer_question(
    id: str,
    msg_id: str,
    body: AnswerIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    owner_id: str = Depends(get_owner_id),  # noqa: B008
    bus: MessageBus = Depends(get_bus),  # noqa: B008
):
    _read_item_or_404(uow, id)  # owner-scoped thread existence
    try:
        message = uow.messages.read(msg_id)
    except RecordNotFound as exc:
        raise HTTPException(status_code=404, detail="message not found") from exc
    if message.thread_id != id or message.kind is not MessageKind.QUESTION:
        raise HTTPException(status_code=404, detail="not a question in this thread")
    if message.payload.get("resolved_option") is not None:
        raise HTTPException(status_code=409, detail="question already resolved")
    if not is_valid_option(message.payload, body.option):
        raise HTTPException(status_code=422, detail="invalid option")
    run_id = message.payload.get("run_id")
    if run_id:
        uow.runs.read(run_id)  # owner-scoped 404 if foreign
        bus.publish(AgentMessage(
            owner_id=owner_id,
            run_id=run_id,
            recipient=recipient_key(run_id, "lead"),
            role="lead",
            type=MessageType.GATE_RESOLVED,
            payload={"decision": body.option},
        ))
    return ok(_message_out(message))
