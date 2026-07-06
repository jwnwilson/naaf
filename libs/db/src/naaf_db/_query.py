from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, asc, desc, func, select


def to_dto(dto: type[BaseModel], row: Any) -> BaseModel:
    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    return dto(**data)


def base_select(orm_model: type[Any], required_filters: dict[str, Any]) -> Select:
    query = select(orm_model)
    for key, value in required_filters.items():
        query = query.where(getattr(orm_model, key) == value)
    return query


def apply_filters(orm_model: type[Any], query: Select, filters: dict[str, Any]) -> Select:
    for key, value in filters.items():
        if key.endswith("__in"):
            query = query.where(getattr(orm_model, key[:-4]).in_(value))
        elif key.endswith("__like"):
            query = query.where(getattr(orm_model, key[:-6]).ilike(f"%{value}%"))
        elif key.endswith("__isnull"):
            attr = getattr(orm_model, key[:-8])
            query = query.where(attr.is_(None) if value else attr.isnot(None))
        elif key.endswith("__gte"):
            query = query.where(getattr(orm_model, key[:-5]) >= value)
        elif key.endswith("__lte"):
            query = query.where(getattr(orm_model, key[:-5]) <= value)
        elif key.endswith("__gt"):
            query = query.where(getattr(orm_model, key[:-4]) > value)
        elif key.endswith("__lt"):
            query = query.where(getattr(orm_model, key[:-4]) < value)
        elif key.endswith("__ne"):
            query = query.where(getattr(orm_model, key[:-4]) != value)
        else:
            query = query.where(getattr(orm_model, key) == value)
    return query


def order(query: Select, order_by: str | None) -> Select:
    if not order_by:
        return query
    direction = desc if order_by.startswith("-") else asc
    return query.order_by(direction(order_by.lstrip("-")))


def count_select(
    orm_model: type[Any], required_filters: dict[str, Any], filters: dict[str, Any]
) -> Select:
    query = apply_filters(orm_model, select(func.count()).select_from(orm_model), filters)
    for key, value in required_filters.items():
        query = query.where(getattr(orm_model, key) == value)
    return query
