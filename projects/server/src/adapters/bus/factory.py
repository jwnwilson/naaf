from typing import TYPE_CHECKING

from adapters.bus.ports import MessageBus
from adapters.bus.sql import SqlMessageBus

if TYPE_CHECKING:
    from adapters.database.uow import SqlUnitOfWork


def build_message_bus(uow: "SqlUnitOfWork") -> MessageBus:
    """Factory for the active MessageBus implementation.
    Swap this to change the queue backend (Redis, RabbitMQ, etc.)."""
    return SqlMessageBus(uow)
