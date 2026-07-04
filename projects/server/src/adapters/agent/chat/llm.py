from domain.agent.llm import LLMAdapter, LLMMessage, LLMRequest, MessageRole
from domain.messaging.chat import ChatTurn

_PERSONA = (
    "You are the {role} agent on a software team, collaborating in a task thread. "
    "Reply concisely to the latest message. You may @mention another role "
    "(lead, architect, backend, frontend, qa, devops) to hand off or ask a question."
)


def _transcript(history: list[ChatTurn]) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in history)


class LlmChatResponder:
    def __init__(self, llm: LLMAdapter, model: str = ""):
        self._llm = llm
        self._model = model

    def set_event_sink(self, emit) -> None:
        setter = getattr(self._llm, "set_event_sink", None)
        if setter is not None:
            setter(emit)

    def respond(self, role: str, history: list[ChatTurn], title: str) -> str:
        request = LLMRequest(
            model=self._model,
            system=_PERSONA.format(role=role),
            messages=[
                LLMMessage(
                    role=MessageRole.USER,
                    content=(
                        f"Task: {title}\n\n"
                        f"Thread so far:\n{_transcript(history)}\n\n"
                        f"Reply as @{role}."
                    ),
                ),
            ],
        )
        return self._llm.complete(request).content
