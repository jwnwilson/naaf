"""LLM-backed lead orchestrator: plans work by driving the orchestration tools."""

from domain.agent.llm import LLMAdapter
from domain.agent.orchestration import (
    ORCHESTRATION_TOOL_SPECS,
    OrchestrationTools,
    execute_orchestration_tool,
)
from domain.agent.tool_loop import run_tool_loop
from domain.messaging.chat import ChatTurn

_SYSTEM = (
    "You are the lead agent for a software project. Break the user's request into a plan and "
    "create it with the tools: an epic, its features, and tasks under those features. Call "
    "list_board first to see what already exists and to pick correct parents (a feature's parent "
    "is an epic; a task's parent is a feature). After creating tasks, call propose_run on the task "
    "ids to ask the human to start development. Finish with a short summary of what you created."
)


def _transcript(history: list[ChatTurn]) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in history)


class LlmOrchestrator:
    def __init__(self, llm: LLMAdapter, model: str = "") -> None:
        self._llm = llm
        self._model = model

    def set_event_sink(self, emit) -> None:
        setter = getattr(self._llm, "set_event_sink", None)
        if setter is not None:
            setter(emit)

    def respond(self, history: list[ChatTurn], title: str, tools: OrchestrationTools) -> str:
        user = (
            f"Project: {title}\n\nConversation so far:\n{_transcript(history)}\n\n"
            "Plan and create the work now."
        )
        text, _tokens = run_tool_loop(
            self._llm,
            model=self._model,
            system=_SYSTEM,
            user=user,
            tool_specs=ORCHESTRATION_TOOL_SPECS,
            execute=lambda call: execute_orchestration_tool(tools, call),
        )
        return text
