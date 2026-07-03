from domain.messaging.chat import ChatTurn


class EchoChatResponder:
    """Deterministic ChatResponder for offline/tests. Optionally mentions a
    partner role so fan-out/loop-guard behaviour can be driven without an LLM."""

    def __init__(self, mention: str | None = None):
        self._mention = mention

    def respond(self, role: str, history: list[ChatTurn], title: str) -> str:
        text = f"[{role}] ack"
        if self._mention:
            text += f" @{self._mention}"
        return text
