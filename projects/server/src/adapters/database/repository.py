from typing import Any, Generic, TypeVar

from domain.errors import IntegrityConflict, RecordNotFound
from pydantic import BaseModel
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.exc import IntegrityError as SqlIntegrityError
from sqlalchemy.orm import Session

from adapters.database.orm import Base
from adapters.database.ports import PaginatedResult

DTO = TypeVar("DTO", bound=BaseModel)


class SqlRepository(Generic[DTO]):  # noqa: UP046
    """Generic DTO-in/DTO-out repository. Subclass and set orm_model + dto."""

    orm_model: type[Base]
    dto: type[BaseModel]

    def __init__(self, session: Session, required_filters: dict[str, Any] | None = None):
        self.session = session
        self.required_filters = required_filters or {}

    # --- mapping -----------------------------------------------------------
    def _to_dto(self, row: Base) -> DTO:
        data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        return self.dto(**data)  # type: ignore[return-value]

    # --- query building ----------------------------------------------------
    def _base_select(self) -> Select:
        query = select(self.orm_model)
        for key, value in self.required_filters.items():
            query = query.where(getattr(self.orm_model, key) == value)
        return query

    def _apply_filters(self, query: Select, filters: dict[str, Any]) -> Select:
        for key, value in filters.items():
            if key.endswith("__in"):
                query = query.where(getattr(self.orm_model, key[:-4]).in_(value))
            elif key.endswith("__like"):
                query = query.where(getattr(self.orm_model, key[:-6]).ilike(f"%{value}%"))
            elif key.endswith("__isnull"):
                attr = getattr(self.orm_model, key[:-8])
                query = query.where(attr.is_(None) if value else attr.isnot(None))
            elif key.endswith("__gte"):
                query = query.where(getattr(self.orm_model, key[:-5]) >= value)
            elif key.endswith("__lte"):
                query = query.where(getattr(self.orm_model, key[:-5]) <= value)
            elif key.endswith("__gt"):
                query = query.where(getattr(self.orm_model, key[:-4]) > value)
            elif key.endswith("__lt"):
                query = query.where(getattr(self.orm_model, key[:-4]) < value)
            elif key.endswith("__ne"):
                query = query.where(getattr(self.orm_model, key[:-4]) != value)
            else:
                query = query.where(getattr(self.orm_model, key) == value)
        return query

    def _order(self, query: Select, order_by: str | None) -> Select:
        if not order_by:
            return query
        direction = desc if order_by.startswith("-") else asc
        return query.order_by(direction(order_by.lstrip("-")))

    def _get_one_row(self, id: str) -> Base:
        query = self._base_select().where(self.orm_model.id == id)
        row = self.session.execute(query).scalar_one_or_none()
        if row is None:
            raise RecordNotFound(f"{self.orm_model.__name__} {id} not found")
        return row

    # --- CRUD --------------------------------------------------------------
    def create(self, dto: BaseModel) -> DTO:
        data = {k: v for k, v in dto.model_dump().items() if v is not None}
        data.update(self.required_filters)  # stamp owner_id (and any scope)
        row = self.orm_model(**data)
        self.session.add(row)
        try:
            self.session.flush()
        except SqlIntegrityError as err:
            self.session.rollback()
            raise IntegrityConflict(str(err.orig)) from err
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
        query = self._apply_filters(self._base_select(), filters)
        query = self._order(query, order_by)

        count_query = self._apply_filters(
            select(func.count()).select_from(self.orm_model), filters
        )
        for key, value in self.required_filters.items():
            count_query = count_query.where(getattr(self.orm_model, key) == value)
        total = int(self.session.execute(count_query).scalar_one())

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
            raise IntegrityConflict(str(err.orig)) from err
        self.session.refresh(row)
        return self._to_dto(row)

    def delete(self, id: str) -> None:
        row = self._get_one_row(id)
        self.session.delete(row)
        self.session.flush()
