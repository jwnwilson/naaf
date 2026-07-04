from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

DTO = TypeVar("DTO")


class PaginatedResult(BaseModel, Generic[DTO]):  # noqa: UP046
    results: list[DTO]
    total: int
    page_size: int
    page_number: int


class Repository(Protocol[DTO]):
    def create(self, dto: BaseModel) -> DTO: ...
    def read(self, id: str) -> DTO: ...
    def read_multi(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str = "-created_at",
    ) -> PaginatedResult[DTO]: ...
    def update(self, id: str, dto: BaseModel) -> DTO: ...
    def delete(self, id: str) -> None: ...


class UnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager[Any]: ...

    @property
    def projects(self) -> Repository: ...
    @property
    def work_items(self) -> Repository: ...
    @property
    def teams(self) -> Repository: ...
    @property
    def agent_definitions(self) -> Repository: ...
    @property
    def runs(self) -> Repository: ...
    @property
    def run_events(self) -> Repository: ...
    @property
    def agent_events(self) -> Repository: ...
    @property
    def notifications(self) -> Repository: ...
    @property
    def messages(self) -> Repository: ...
