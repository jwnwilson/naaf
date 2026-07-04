from adapters.agent.claude_cli.stream_runner import parse_stream_line, streaming_runner


def test_parse_text_block():
    line = '{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"}]}}'
    assert parse_stream_line(line) == [("text_block", {"text": "Hello"})]


def test_parse_tool_call():
    line = (
        '{"type":"assistant","message":{"content":['
        '{"type":"tool_use","name":"create_task","input":{"title":"x"}}]}}'
    )
    assert parse_stream_line(line) == [
        ("tool_call", {"name": "create_task", "input": {"title": "x"}})
    ]


def test_parse_tool_result():
    line = '{"type":"user","message":{"content":[{"type":"tool_result","content":"ok"}]}}'
    assert parse_stream_line(line) == [("tool_result", {"result": "ok"})]


def test_parse_result_line_is_terminal_not_an_event():
    line = '{"type":"result","result":"done","is_error":false,"usage":{"input_tokens":3}}'
    assert parse_stream_line(line) == []  # terminal handled by the runner, not emitted here


def test_parse_bad_line_is_ignored():
    assert parse_stream_line("not json") == []


class _FakeProc:
    def __init__(self, lines):
        self.stdout = iter(lines)
        self.returncode = 0

    def wait(self, timeout=None):
        return 0


def test_streaming_runner_emits_events_and_returns_final():
    lines = [
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Hi"}]}}\n',
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"list_board","input":{}}]}}\n',
        '{"type":"user","message":{"content":[{"type":"tool_result","content":"[]"}]}}\n',
        '{"type":"result","result":"all done","is_error":false,"usage":{"output_tokens":5}}\n',
    ]
    seen = []
    data = streaming_runner(
        ["claude"], emit=lambda k, p: seen.append((k, p)),
        _popen=lambda *a, **k: _FakeProc(lines),
    )
    assert [k for k, _ in seen] == ["text_block", "tool_call", "tool_result"]
    assert data["result"] == "all done"
    assert data["is_error"] is False
    assert data["usage"] == {"output_tokens": 5}
