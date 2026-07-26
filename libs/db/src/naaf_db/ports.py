from __future__ import annotations

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
