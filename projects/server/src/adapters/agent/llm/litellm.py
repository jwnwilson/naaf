import json

from domain.agent.llm import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ToolCall,
    Usage,
)


class LiteLLMAdapter:
    """LLMAdapter backed by a LiteLLM gateway (OpenAI-compatible /chat/completions)."""

    def __init__(self, base_url: str, key: str, client=None):
        self._base_url = base_url.rstrip("/")
        self._key = key
        self._client = client  # lazily built in complete() when None

    def complete(self, request: LLMRequest) -> LLMResponse:
        payload: dict = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": self._to_openai_messages(request),
        }
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in request.tools
            ]
        client = self._client
        if client is None:
            import httpx

            client = httpx.Client(timeout=600)
        resp = client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self._key}"},
        )
        body = resp.json()
        choice = body["choices"][0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        tool_calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                args=json.loads(tc["function"]["arguments"] or "{}"),
            )
            for tc in (message.get("tool_calls") or [])
        ]
        stop_reason = "tool_use" if choice.get("finish_reason") == "tool_calls" else "end_turn"
        usage = body.get("usage") or {}
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=Usage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            ),
        )

    def _to_openai_messages(self, request: LLMRequest) -> list[dict]:
        out: list[dict] = []
        if request.system:
            out.append({"role": "system", "content": request.system})
        for m in request.messages:
            out.append(self._to_openai(m))
        return out

    @staticmethod
    def _to_openai(m: LLMMessage) -> dict:
        if m.role is MessageRole.TOOL:
            return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
        if m.role is MessageRole.ASSISTANT and m.tool_calls:
            return {
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.args)},
                    }
                    for c in m.tool_calls
                ],
            }
        role = "assistant" if m.role is MessageRole.ASSISTANT else "user"
        return {"role": role, "content": m.content}
