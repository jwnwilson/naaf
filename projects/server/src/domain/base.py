from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    """A 32-char UUID hex string used for all entity IDs."""
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Entity(BaseModel):
    """Base for all domain entities. Immutable updates via model_copy."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=new_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None
