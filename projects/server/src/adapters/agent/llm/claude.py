from domain.agent.llm import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ToolCall,
    Usage,
)

_MAX_TOKENS_CAP = 16000


class ClaudeLLMAdapter:
    def __init__(
        self,
        api_key: str,
        base_url: str = "",
        aliases: dict[str, str] | None = None,
        client=None,
    ):
        self._aliases = aliases or {}
        if client is not None:
            self._client = client
        else:
            import anthropic

            kwargs: dict = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = anthropic.Anthropic(**kwargs)

    def complete(self, request: LLMRequest) -> LLMResponse:
        reply = self._client.messages.create(
            model=self._aliases.get(request.model, request.model),
            max_tokens=min(request.max_tokens, _MAX_TOKENS_CAP),
            system=request.system,
            tools=[
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in request.tools
            ],
            messages=[self._to_anthropic(m) for m in request.messages],
        )
        text = "".join(b.text for b in reply.content if getattr(b, "type", "") == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, args=dict(b.input))
            for b in reply.content
            if getattr(b, "type", "") == "tool_use"
        ]
        return LLMResponse(
            content=text,
            tool_calls=tool_calls,
            stop_reason=reply.stop_reason,
            usage=Usage(
                input_tokens=reply.usage.input_tokens,
                output_tokens=reply.usage.output_tokens,
            ),
        )

    @staticmethod
    def _to_anthropic(m: LLMMessage) -> dict:
        if m.role is MessageRole.TOOL:
            return {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                ],
            }
        if m.role is MessageRole.ASSISTANT and m.tool_calls:
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.args}
                for c in m.tool_calls
            ]
            return {"role": "assistant", "content": blocks}
        role = "assistant" if m.role is MessageRole.ASSISTANT else "user"
        return {"role": role, "content": m.content}
