import json
from enum import Enum
from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.types import DecoratedCallable
from pydantic import BaseModel

from crud_router.envelope import Envelope, ok


class CrudRouter(APIRouter):
    """Envelope-aware CRUD router (sync). Ported from hexrepo libs/api crud.py.

    Each handler returns an Envelope; persistence errors are NOT caught here —
    the host app registers exception handlers that emit the envelope (see
    interactors/api/envelope_handlers.py).
    """

    def __init__(
        self,
        db_dependency: Callable[[], Any],
        repository: str,
        response_dto: type[BaseModel],
        create_schema: type[BaseModel],
        update_schema: type[BaseModel],
        methods: list[str],
        prefix: str | None = None,
        tags: list[str | Enum] | None = None,
        **kwargs: Any,
    ):
        self.db_dependency = db_dependency
        self.repository = repository
        self.response_dto = response_dto
        self.create_schema = create_schema
        self.update_schema = update_schema
        self.methods = methods or ["READ"]
        super().__init__(prefix=prefix or "", tags=tags, redirect_slashes=True, **kwargs)
        self._setup_routes()

    def _repo(self, uow: Any) -> Any:
        return getattr(uow, self.repository)

    def _setup_routes(self) -> None:
        if "CREATE" in self.methods:
            self.add_api_route(
                "/", self._create(), methods=["POST"], status_code=201,
                response_model=Envelope[self.response_dto],  # type: ignore[name-defined]
            )
        if "READ" in self.methods:
            self.add_api_route(
                "/{id}", self._read(), methods=["GET"],
                response_model=Envelope[self.response_dto],  # type: ignore[name-defined]
            )
            self.add_api_route(
                "/", self._read_multi(), methods=["GET"],
                response_model=Envelope[list[self.response_dto]],  # type: ignore[name-defined]
            )
        if "UPDATE" in self.methods:
            self.add_api_route(
                "/{id}", self._update(), methods=["PATCH"],
                response_model=Envelope[self.response_dto],  # type: ignore[name-defined]
            )
        if "DELETE" in self.methods:
            self.add_api_route(
                "/{id}", self._delete(), methods=["DELETE"], status_code=204,
                response_class=Response,
            )

    def _create(self) -> Callable:
        def create_record(obj_in: self.create_schema, uow=Depends(self.db_dependency)):  # type: ignore[name-defined]
            return ok(self._repo(uow).create(obj_in))
        return create_record

    def _read(self) -> Callable:
        def read_record(id: UUID, uow=Depends(self.db_dependency)):
            return ok(self._repo(uow).read(id.hex))
        return read_record

    def _read_multi(self) -> Callable:
        def read_multiple(
            uow=Depends(self.db_dependency),
            filters: str = "{}",
            page_size: int = 50,
            page_number: int = 1,
            order_by: str = "-created_at",
        ):
            page = self._repo(uow).read_multi(
                filters=json.loads(filters),
                page_size=page_size,
                page_number=page_number,
                order_by=order_by,
            )
            return ok(page.results, meta={
                "total": page.total,
                "page_size": page.page_size,
                "page_number": page.page_number,
            })
        return read_multiple

    def _update(self) -> Callable:
        def update_record(id: UUID, obj_in: self.update_schema, uow=Depends(self.db_dependency)):  # type: ignore[name-defined]
            return ok(self._repo(uow).update(id.hex, obj_in))
        return update_record

    def _delete(self) -> Callable:
        def delete_record(id: UUID, uow=Depends(self.db_dependency)):
            self._repo(uow).delete(id.hex)
            return Response(status_code=204)
        return delete_record

    def remove_api_route(self, path: str, methods: list[str]) -> None:
        methods_ = set(methods)
        for route in list(self.routes):
            if route.path == f"{self.prefix}{path}" and route.methods == methods_:  # type: ignore[attr-defined]
                self.routes.remove(route)

    def post(self, path: str, *args: Any, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        self.remove_api_route(path, ["POST"])
        return super().post(path, *args, **kwargs)

    def get(self, path: str, *args: Any, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        self.remove_api_route(path, ["GET"])
        return super().get(path, *args, **kwargs)

    def patch(self, path: str, *args: Any, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        self.remove_api_route(path, ["PATCH"])
        return super().patch(path, *args, **kwargs)

    def delete(self, path: str, *args: Any, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        self.remove_api_route(path, ["DELETE"])
        return super().delete(path, *args, **kwargs)
