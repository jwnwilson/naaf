from domain.agent.llm import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ToolCall,
    Usage,
)


def test_llm_request_defaults_are_empty_and_immutable():
    req = LLMRequest(model="opus", system="be terse", messages=[])
    assert req.tools == []
    assert req.max_tokens == 8192
    updated = req.model_copy(update={"max_tokens": 100})
    assert req.max_tokens == 8192 and updated.max_tokens == 100  # original unchanged


def test_llm_response_carries_tool_calls_and_usage():
    resp = LLMResponse(
        tool_calls=[ToolCall(id="t1", name="bash", args={"cmd": "ls"})],
        stop_reason="tool_use",
        usage=Usage(input_tokens=10, output_tokens=3),
    )
    assert resp.tool_calls[0].name == "bash"
    assert resp.usage.output_tokens == 3


def test_message_role_values():
    assert MessageRole.TOOL == "tool"
    msg = LLMMessage(role=MessageRole.USER, content="hi")
    assert msg.tool_calls == []
