from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):  # noqa: UP046
    success: bool = True
    data: T | None = None
    error: str | None = None
    meta: dict | None = None


def ok(data, meta: dict | None = None) -> Envelope:
    return Envelope(success=True, data=data, meta=meta)


def fail(error: str) -> Envelope:
    return Envelope(success=False, data=None, error=error)
