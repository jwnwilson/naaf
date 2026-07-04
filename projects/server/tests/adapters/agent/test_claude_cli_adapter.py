from adapters.agent.claude_cli.adapter import ClaudeCliLLMAdapter
from domain.agent.llm import LLMMessage, LLMRequest, MessageRole, ToolSpec

REPORT = ToolSpec(name="report", description="", parameters={"type": "object", "properties": {}})


def _adapter(result_json, capture=None, **kw):
    def runner(argv, *, cwd=None, env=None, timeout=None):
        if capture is not None:
            capture["argv"] = argv
            capture["env"] = env
        return result_json
    return ClaudeCliLLMAdapter(runner=runner, **kw)


def _req(system="", tools=None, content="do it"):
    return LLMRequest(
        model="m", system=system,
        messages=[LLMMessage(role=MessageRole.USER, content=content)],
        tools=tools or [],
    )


def test_chat_path_returns_text_and_usage():
    a = _adapter({"result": "hello reply", "is_error": False,
                  "usage": {"input_tokens": 10, "output_tokens": 5}})
    resp = a.complete(_req())
    assert resp.content == "hello reply"
    assert resp.tool_calls == []
    assert resp.usage.input_tokens == 10 and resp.usage.output_tokens == 5


def test_stage_pass_verdict_synthesizes_report_passed():
    a = _adapter({"result": "did it.\nVERDICT: PASS — all tests green", "usage": {}})
    resp = a.complete(_req(tools=[REPORT]))
    assert [tc.name for tc in resp.tool_calls] == ["report"]
    assert resp.tool_calls[0].args["passed"] is True
    assert resp.tool_calls[0].args["summary"]


def test_stage_fail_verdict():
    a = _adapter({"result": "VERDICT: FAIL — tests broke", "usage": {}})
    resp = a.complete(_req(tools=[REPORT]))
    assert resp.tool_calls[0].args["passed"] is False


def test_stage_no_verdict_omits_passed_for_runtime_default():
    a = _adapter({"result": "plan written", "usage": {}})
    resp = a.complete(_req(tools=[REPORT]))
    assert "passed" not in resp.tool_calls[0].args


def test_error_result_marks_stage_failed():
    a = _adapter({"result": "boom", "is_error": True, "usage": {}})
    resp = a.complete(_req(tools=[REPORT]))
    assert resp.tool_calls[0].args["passed"] is False


def test_argv_includes_permission_mcp_and_workdir_flags():
    cap = {}
    a = _adapter({"result": "ok", "usage": {}}, capture=cap,
                 mcp_config_path="/tmp/mcp.json", cwd="/ws", github_token="ghp_x")
    a.complete(_req())
    argv = cap["argv"]
    assert "-p" in argv and "bypassPermissions" in argv
    assert "--mcp-config" in argv and "/tmp/mcp.json" in argv
    assert "--add-dir" in argv and "/ws" in argv
    assert cap["env"].get("GH_TOKEN") == "ghp_x"


def test_default_path_uses_streaming_runner_when_sink_set(monkeypatch):
    """Regression: streaming branch must select streaming_runner in production (no injected runner).
    Without the fix, self._runner defaults to _default_runner which doesn't accept emit."""
    import adapters.agent.claude_cli.adapter as mod
    called = {}

    def fake_streaming(argv, *, cwd=None, env=None, timeout=None, emit=None):
        called["argv"] = argv
        called["emit"] = emit
        if emit is not None:
            emit("text_block", {"text": "x"})
        return {"result": "ok", "is_error": False, "usage": {}}

    monkeypatch.setattr(mod, "streaming_runner", fake_streaming)
    events = []
    adapter = ClaudeCliLLMAdapter()  # NO runner injected → production path
    adapter.set_event_sink(lambda k, p: events.append((k, p)))
    resp = adapter.complete(_req())
    assert "stream-json" in called["argv"]
    assert called["emit"] is not None
    assert events == [("text_block", {"text": "x"})]
    assert resp.content == "ok"
