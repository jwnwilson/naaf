"""Deterministic lead orchestrator for offline runs and tests.

Creates a single epic from the last user message via the tools capability, so
the project-chat path exercises the tool surface without reaching a model.
"""

from domain.agent.orchestration import OrchestrationTools
from domain.messaging.chat import ChatTurn


class EchoOrchestrator:
    def respond(self, history: list[ChatTurn], title: str, tools: OrchestrationTools) -> str:
        last_user = next((t.content for t in reversed(history) if t.role == "user"), "")
        epic_title = last_user.strip() or "New epic"
        result = tools.create_work_item("epic", epic_title)
        return f"[lead] {result}"
