from typing import Protocol

from domain.runs.messages import AgentMessage
from sqlalchemy.orm import Session


class MessageBus(Protocol):
    def publish(self, msg: AgentMessage, session: Session) -> None: ...
    def claim_next(self, session: Session) -> AgentMessage | None: ...
    def ack(self, msg: AgentMessage, session: Session) -> None: ...
