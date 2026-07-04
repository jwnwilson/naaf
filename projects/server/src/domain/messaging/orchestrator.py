from typing import Protocol

from domain.agent.orchestration import OrchestrationTools
from domain.messaging.chat import ChatTurn


class LeadOrchestrator(Protocol):
    """The project-level lead: reads the conversation and acts via orchestration tools."""

    def respond(self, history: list[ChatTurn], title: str, tools: OrchestrationTools) -> str: ...
