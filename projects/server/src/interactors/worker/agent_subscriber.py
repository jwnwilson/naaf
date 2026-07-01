"""AgentSubscriber — interactor-layer wrapper around the run orchestration dispatch.

Lives in interactors (not domain) because it imports the concrete handlers.dispatch,
which touches adapter types (AgentRuntime, repositories, bus).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.runs.messages import AgentMessage

    from interactors.worker.handlers import HandlerContext


class AgentSubscriber:
    """Subscriber that routes every agent-bus message through the run orchestration."""

    name = "agent"

    def interested_in(self, message: AgentMessage) -> bool:  # type: ignore[override]
        return True

    def handle(self, message: AgentMessage, ctx: HandlerContext) -> None:  # type: ignore[override]
        from interactors.worker.handlers import dispatch
        dispatch(message, ctx)
