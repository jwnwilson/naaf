from collections.abc import Iterator

from adapters.bus.factory import build_message_bus
from adapters.bus.ports import MessageBus
from adapters.database.uow import SqlUnitOfWork
from fastapi import Depends, Request
from storage import Storage

from interactors.api.auth import get_owner_id


def get_uow(request: Request, owner_id: str = Depends(get_owner_id)) -> Iterator[SqlUnitOfWork]:
    uow = SqlUnitOfWork(
        request.app.state.session_factory,
        required_filters={"owner_id": owner_id},
    )
    with uow.transaction():
        yield uow


def get_bus(uow: SqlUnitOfWork = Depends(get_uow)) -> MessageBus:  # noqa: B008
    """Build the message bus from the request's uow.

    FastAPI shares the single get_uow result within a request, so the bus and
    the route's uow use the SAME session/transaction — the enqueue stays atomic
    with the run/work-item writes.
    """
    return build_message_bus(uow)


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


def get_max_attachment_bytes(request: Request) -> int:
    return request.app.state.settings.max_attachment_bytes
