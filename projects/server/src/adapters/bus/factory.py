from sqlalchemy.orm import Session

from adapters.bus.ports import MessageBus
from adapters.bus.sql import SqlMessageBus


def build_message_bus(session: Session) -> MessageBus:
    """Factory that returns the active MessageBus implementation.
    Swap this to change the queue backend (Redis, RabbitMQ, etc.)."""
    return SqlMessageBus(session)
