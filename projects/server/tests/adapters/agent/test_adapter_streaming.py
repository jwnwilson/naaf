from adapters.agent.claude_cli.adapter import ClaudeCliLLMAdapter
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole


def _req():
    return LLMRequest(model="m", messages=[LLMMessage(role=MessageRole.USER, content="hi")])


def test_no_sink_uses_json_format_and_no_emit_kwarg():
    seen = {}

    def runner(argv, *, cwd=None, env=None, timeout=None):  # note: no emit kwarg
        seen["argv"] = argv
        return {"result": "ok", "usage": {}}

    ClaudeCliLLMAdapter(runner=runner).complete(_req())
    assert "--output-format" in seen["argv"]
    i = seen["argv"].index("--output-format")
    assert seen["argv"][i + 1] == "json"


def test_sink_switches_to_stream_json_and_forwards_emit():
    seen = {}

    def runner(argv, *, cwd=None, env=None, timeout=None, emit=None):
        seen["argv"] = argv
        emit("text_block", {"text": "streamed"})
        return {"result": "final", "usage": {}}

    events = []
    adapter = ClaudeCliLLMAdapter(runner=runner)
    adapter.set_event_sink(lambda k, p: events.append((k, p)))
    resp = adapter.complete(_req())
    i = seen["argv"].index("--output-format")
    assert seen["argv"][i + 1] == "stream-json"
    assert "--verbose" in seen["argv"]
    assert events == [("text_block", {"text": "streamed"})]
    assert resp.content == "final"
