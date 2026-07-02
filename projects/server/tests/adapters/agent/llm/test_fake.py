from adapters.agent.llm.fake import FakeLLMAdapter
from domain.agent.llm import LLMRequest, LLMResponse, ToolCall


def test_fake_returns_scripted_responses_in_order():
    fake = FakeLLMAdapter([
        LLMResponse(tool_calls=[ToolCall(id="t1", name="bash", args={"cmd": "ls"})],
                    stop_reason="tool_use"),
        LLMResponse(content="done", stop_reason="end_turn"),
    ])
    r1 = fake.complete(LLMRequest(model="m", messages=[]))
    r2 = fake.complete(LLMRequest(model="m", messages=[]))
    assert r1.stop_reason == "tool_use"
    assert r2.content == "done"
    assert len(fake.requests) == 2
