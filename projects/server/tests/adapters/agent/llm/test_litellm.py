import json

from adapters.agent.llm.litellm import LiteLLMAdapter
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole, ToolCall, ToolSpec


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, body):
        self._body = body
        self.seen = None

    def post(self, url, json, headers):
        self.seen = {"url": url, "json": json, "headers": headers}
        return _FakeResp(self._body)


def _text_body(text):
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 2},
    }


def _tool_body():
    return {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "tc1",
                            "type": "function",
                            "function": {"name": "bash", "arguments": json.dumps({"cmd": "ls"})},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }


def test_translates_text_reply_and_usage():
    client = _FakeClient(_text_body("hello"))
    adapter = LiteLLMAdapter(base_url="http://lite:4000", key="k", client=client)
    resp = adapter.complete(
        LLMRequest(
            model="gpt",
            system="s",
            messages=[LLMMessage(role=MessageRole.USER, content="hi")],
        )
    )
    assert resp.content == "hello"
    assert resp.stop_reason == "end_turn"
    assert resp.usage.input_tokens == 7 and resp.usage.output_tokens == 2
    assert client.seen["url"] == "http://lite:4000/chat/completions"
    assert client.seen["headers"]["Authorization"] == "Bearer k"
    assert client.seen["json"]["messages"][0] == {"role": "system", "content": "s"}


def test_translates_tool_calls_reply():
    adapter = LiteLLMAdapter(
        base_url="http://lite:4000/", key="k", client=_FakeClient(_tool_body())
    )
    resp = adapter.complete(
        LLMRequest(
            model="gpt",
            messages=[],
            tools=[ToolSpec(name="bash", description="d", parameters={"type": "object"})],
        )
    )
    assert resp.stop_reason == "tool_use"
    assert resp.tool_calls[0].name == "bash" and resp.tool_calls[0].args == {"cmd": "ls"}
    assert resp.content == ""


def test_outbound_tool_result_and_assistant_tool_calls():
    client = _FakeClient(_text_body(""))
    adapter = LiteLLMAdapter(base_url="http://lite:4000", key="k", client=client)
    adapter.complete(
        LLMRequest(
            model="gpt",
            system="",
            messages=[
                LLMMessage(
                    role=MessageRole.ASSISTANT,
                    content="calling",
                    tool_calls=[ToolCall(id="tc2", name="bash", args={"cmd": "ls"})],
                ),
                LLMMessage(role=MessageRole.TOOL, content="exit=0", tool_call_id="tc2"),
            ],
        )
    )
    msgs = client.seen["json"]["messages"]
    assistant = next(m for m in msgs if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["function"]["name"] == "bash"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"cmd": "ls"}
    tool_msg = next(m for m in msgs if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "tc2" and tool_msg["content"] == "exit=0"
