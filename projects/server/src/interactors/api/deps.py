from collections.abc import Iterator

from adapters.database.uow import SqlUnitOfWork
from fastapi import Depends, Request

from interactors.api.auth import get_owner_id


def get_uow(request: Request, owner_id: str = Depends(get_owner_id)) -> Iterator[SqlUnitOfWork]:
    uow = SqlUnitOfWork(
        request.app.state.session_factory,
        required_filters={"owner_id": owner_id},
    )
    with uow.transaction():
        yield uow
