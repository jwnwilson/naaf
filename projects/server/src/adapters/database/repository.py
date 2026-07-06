from typing import Generic, TypeVar

from domain.errors import IntegrityConflict, RecordNotFound
from naaf_db.repository import SqlRepository as _SqlRepository
from pydantic import BaseModel

DTO = TypeVar("DTO", bound=BaseModel)


class SqlRepository(_SqlRepository[DTO], Generic[DTO]):  # noqa: UP046
    not_found_error = RecordNotFound
    conflict_error = IntegrityConflict
