from enum import StrEnum

from domain.base import Entity


class MessageRole(StrEnum):
    USER = "user"
    AGENT = "agent"
    LEAD_AGENT = "lead_agent"


class Message(Entity):
    owner_id: str
    thread_id: str  # == run_id
    role: MessageRole
    content: str
    agent_id: str | None = None
