from domain.agent.llm import (
    LLMResponse,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)
from domain.agent.tool_loop import run_tool_loop


class ScriptedLLM:
    """Returns queued responses in order; records requests seen."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return self._responses.pop(0)


SPECS = [ToolSpec(name="do_thing", description="", parameters={"type": "object", "properties": {}})]


def test_executes_tool_calls_then_returns_final_text_and_tokens():
    llm = ScriptedLLM([
        LLMResponse(content="working", tool_calls=[ToolCall(id="t1", name="do_thing", args={})],
                    stop_reason="tool_use", usage=Usage(input_tokens=10, output_tokens=5)),
        LLMResponse(content="all done", tool_calls=[], stop_reason="end_turn",
                    usage=Usage(input_tokens=3, output_tokens=2)),
    ])
    executed = []

    def execute(call):
        executed.append(call.name)
        return ToolResult(tool_call_id=call.id, content="ok")

    text, tokens = run_tool_loop(
        llm, model="m", system="sys", user="build it", tool_specs=SPECS, execute=execute,
    )

    assert executed == ["do_thing"]
    assert text == "all done"
    assert tokens == 20  # 10+5 + 3+2


def test_stops_at_max_iterations():
    # Always asks for another tool call — the loop must terminate on max_iterations.
    forever = LLMResponse(content="", tool_calls=[ToolCall(id="t", name="do_thing", args={})],
                          stop_reason="tool_use", usage=Usage(input_tokens=1, output_tokens=1))
    llm = ScriptedLLM([forever] * 10)

    text, tokens = run_tool_loop(
        llm, model="m", system="", user="go", tool_specs=SPECS,
        execute=lambda c: ToolResult(tool_call_id=c.id, content="ok"), max_iterations=3,
    )
    assert len(llm.requests) == 3
