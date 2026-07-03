from typing import TYPE_CHECKING

from domain.runs.messages import AgentMessage

if TYPE_CHECKING:
    from adapters.database.uow import SqlUnitOfWork


class SqlMessageBus:
    """MessageBus port adapter — delegates to the UoW's bus_messages repository.

    Contains no SQL: all persistence lives in adapters/database BusMessageRepository.
    """

    def __init__(self, uow: "SqlUnitOfWork") -> None:
        self._uow = uow

    def publish(self, msg: AgentMessage) -> None:
        self._uow.bus_messages.publish(msg)

    def claim_next(self, roles: list[str] | None = None) -> AgentMessage | None:
        return self._uow.bus_messages.claim_next(roles)

    def ack(self, msg: AgentMessage) -> None:
        self._uow.bus_messages.ack(msg)
