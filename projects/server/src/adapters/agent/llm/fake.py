from domain.agent.llm import LLMRequest, LLMResponse


class FakeLLMAdapter:
    """Scripted LLMAdapter for offline tests. Returns responses in order."""

    def __init__(self, scripted: list[LLMResponse]):
        self._scripted = list(scripted)
        self._i = 0
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        resp = self._scripted[self._i]
        self._i += 1
        return resp
