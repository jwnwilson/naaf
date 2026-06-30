from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.base import new_id, utcnow


class MessageType(StrEnum):
    START = "start"
    RUN_STAGE = "run_stage"
    STAGE_REPORT = "stage_report"
    GATE_RESOLVED = "gate_resolved"


class MessageStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    DONE = "done"


def recipient_key(run_id: str, role: str) -> str:
    return f"run:{run_id}:{role}"


class AgentMessage(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    run_id: str
    recipient: str
    role: str
    type: MessageType
    payload: dict = Field(default_factory=dict)
    status: MessageStatus = MessageStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    claimed_at: datetime | None = None
