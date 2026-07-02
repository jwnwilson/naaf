from types import SimpleNamespace

from adapters.agent.llm.claude import ClaudeLLMAdapter
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole, ToolSpec


class _FakeMessages:
    def __init__(self, reply):
        self._reply = reply
        self.seen = None

    def create(self, **kwargs):
        self.seen = kwargs
        return self._reply


class _FakeClient:
    def __init__(self, reply): self.messages = _FakeMessages(reply)


def _reply(blocks, stop="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=7, output_tokens=2))


def test_translates_text_reply_and_usage():
    reply = _reply([SimpleNamespace(type="text", text="hello")])
    adapter = ClaudeLLMAdapter(api_key="k", aliases={"sonnet": "claude-sonnet-4-6"},
                               client=_FakeClient(reply))
    resp = adapter.complete(LLMRequest(model="sonnet", system="s",
                                       messages=[LLMMessage(role=MessageRole.USER, content="hi")]))
    assert resp.content == "hello"
    assert resp.usage.input_tokens == 7
    assert adapter._client.messages.seen["model"] == "claude-sonnet-4-6"  # alias resolved


def test_translates_tool_use_block_into_toolcall():
    reply = _reply([SimpleNamespace(type="tool_use", id="tu1", name="bash", input={"cmd": "ls"})],
                   stop="tool_use")
    adapter = ClaudeLLMAdapter(api_key="k", client=_FakeClient(reply))
    resp = adapter.complete(LLMRequest(model="claude-opus-4-8", system="",
                                       messages=[], tools=[ToolSpec(name="bash",
                                       description="d", parameters={"type": "object"})]))
    assert resp.stop_reason == "tool_use"
    assert resp.tool_calls[0].name == "bash" and resp.tool_calls[0].args == {"cmd": "ls"}
    assert adapter._client.messages.seen["tools"][0]["name"] == "bash"
