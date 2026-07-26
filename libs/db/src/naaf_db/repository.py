from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel
from sqlalchemy import Delete
from sqlalchemy import delete as sql_delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError as SqlIntegrityError
from sqlalchemy.orm import Session

from naaf_db import _query
from naaf_db.errors import IntegrityConflict, RecordNotFound
from naaf_db.ports import PaginatedResult

DTO = TypeVar("DTO", bound=BaseModel)


class SqlRepository(Generic[DTO]):  # noqa: UP046
    """Generic DTO-in/DTO-out repository. Subclass and set orm_model + dto.

    Subclasses may override not_found_error / conflict_error to raise
    application-specific exceptions (e.g. the app binds them to domain.errors).
    """

    orm_model: type[Any]
    dto: type[BaseModel]
    not_found_error: type[Exception] = RecordNotFound
    conflict_error: type[Exception] = IntegrityConflict

    def __init__(self, session: Session, required_filters: dict[str, Any] | None = None):
        self.session = session
        self.required_filters = required_filters or {}

    def _to_dto(self, row: Any) -> DTO:
        return cast(DTO, _query.to_dto(self.dto, row))

    def _get_one_row(self, id: str) -> Any:
        query = _query.base_select(self.orm_model, self.required_filters).where(
            self.orm_model.id == id
        )
        row = self.session.execute(query).scalar_one_or_none()
        if row is None:
            raise self.not_found_error(f"{self.orm_model.__name__} {id} not found")
        return row

    def create(self, dto: BaseModel) -> DTO:
        data = {k: v for k, v in dto.model_dump().items() if v is not None}
        data.update(self.required_filters)
        row = self.orm_model(**data)
        self.session.add(row)
        try:
            self.session.flush()
        except SqlIntegrityError as err:
            self.session.rollback()
            raise self.conflict_error(str(err.orig)) from err
        self.session.refresh(row)
        return self._to_dto(row)

    def read(self, id: str) -> DTO:
        return self._to_dto(self._get_one_row(id))

    def read_multi(
        self,
        filters: dict[str, Any] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        order_by: str = "-created_at",
    ) -> PaginatedResult[DTO]:
        filters = filters or {}
        query = _query.order(
            _query.apply_filters(
                self.orm_model, _query.base_select(self.orm_model, self.required_filters), filters
            ),
            order_by,
        )
        total = int(self.session.execute(
            _query.count_select(self.orm_model, self.required_filters, filters)
        ).scalar_one())
        if page_size > 0 and page_number >= 1:
            query = query.offset((page_number - 1) * page_size).limit(page_size)
        rows = self.session.execute(query).scalars().all()
        return PaginatedResult[self.dto](  # type: ignore[name-defined]
            results=[self._to_dto(r) for r in rows],
            total=total,
            page_size=page_size,
            page_number=page_number,
        )

    def update(self, id: str, dto: BaseModel) -> DTO:
        row = self._get_one_row(id)
        for key, value in dto.model_dump(exclude_unset=True).items():
            if key in ("id", "owner_id", "created_at"):
                continue
            setattr(row, key, value)
        try:
            self.session.flush()
        except SqlIntegrityError as err:
            self.session.rollback()
            raise self.conflict_error(str(err.orig)) from err
        self.session.refresh(row)
        return self._to_dto(row)

    def delete(self, id: str) -> None:
        row = self._get_one_row(id)
        self.session.delete(row)
        self.session.flush()

    def delete_where(self, **filters: Any) -> int:
        """Bulk-delete rows matching required_filters AND the given filters (equality
        + `__in` suffix). required_filters (owner scope) are applied unconditionally.
        Returns rows deleted."""
        stmt: Delete = sql_delete(self.orm_model)
        for key, value in filters.items():
            if key.endswith("__in"):
                stmt = stmt.where(getattr(self.orm_model, key[:-4]).in_(value))
            else:
                stmt = stmt.where(getattr(self.orm_model, key) == value)
        for key, value in self.required_filters.items():
            stmt = stmt.where(getattr(self.orm_model, key) == value)
        result = cast(CursorResult, self.session.execute(stmt))
        self.session.flush()
        return int(result.rowcount or 0)
