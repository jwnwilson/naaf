from adapters.agent.llm.fake import FakeLLMAdapter
from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.llm import LLMResponse, ToolCall, Usage
from domain.agent.runtime import LlmAgentRuntime
from domain.agent.workspace import CommandResult
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


class _Workspace:
    def __init__(self):
        self.written = {}

    def read(self, path):
        return self.written.get(path, "")

    def write(self, path, content):
        self.written[path] = content

    def edit(self, path, old, new):
        self.written[path] = self.written[path].replace(old, new)

    def grep(self, pattern, path=None):
        return ""

    def bash(self, cmd, timeout_s):
        return CommandResult(exit_code=0, stdout="ok", stderr="")


def _ctx(stage=Stage.IMPLEMENT):
    return StageContext(
        run_id="r",
        role="engineer",
        stage=stage,
        workspace_path="/ws",
        work_item=WorkItemBrief(title="Add X"),
        agent=AgentDefinition(
            owner_id="o",
            team_id="t",
            role=AgentRole.BACKEND,
            model_alias="sonnet",
            token_limit=1000,
        ),
    )


def test_runtime_executes_tool_calls_then_finishes():
    ws = _Workspace()
    llm = FakeLLMAdapter([
        LLMResponse(
            tool_calls=[
                ToolCall(id="t1", name="write_file", args={"path": "a.py", "content": "x=1"})
            ],
            stop_reason="tool_use",
        ),
        LLMResponse(content="Implemented X.", stop_reason="end_turn"),
    ])
    runtime = LlmAgentRuntime(llm=llm, workspace=ws)
    outcome = runtime.run_stage("engineer", Stage.IMPLEMENT, _ctx())
    assert ws.written["a.py"] == "x=1"
    assert outcome.result.passed is True
    assert "Implemented X." in outcome.result.summary
    assert any("write_file" in e.message for e in outcome.events)


def test_runtime_passes_role_model_alias_to_the_request():
    llm = FakeLLMAdapter([LLMResponse(content="done", stop_reason="end_turn")])
    LlmAgentRuntime(llm=llm, workspace=_Workspace()).run_stage(
        "engineer", Stage.PLAN, _ctx(Stage.PLAN)
    )
    assert llm.requests[0].model == "sonnet"
    assert llm.requests[0].max_tokens == 1000


def test_runtime_fails_when_iterations_exhausted():
    # always asks for another tool call -> never terminates within the cap
    loop = [
        LLMResponse(
            tool_calls=[ToolCall(id="t", name="bash", args={"cmd": "ls"})],
            stop_reason="tool_use",
        )
        for _ in range(5)
    ]
    runtime = LlmAgentRuntime(llm=FakeLLMAdapter(loop), workspace=_Workspace(), max_iterations=3)
    outcome = runtime.run_stage("engineer", Stage.IMPLEMENT, _ctx())
    assert outcome.result.passed is False
    assert "iteration" in outcome.result.summary.lower()
    assert outcome.result.tokens == 0


def test_runtime_accumulates_usage_tokens():
    llm = FakeLLMAdapter([
        LLMResponse(
            tool_calls=[ToolCall(id="t1", name="bash", args={"cmd": "ls"})],
            stop_reason="tool_use",
            usage=Usage(input_tokens=10, output_tokens=5),
        ),
        LLMResponse(
            content="done",
            stop_reason="end_turn",
            usage=Usage(input_tokens=8, output_tokens=2),
        ),
    ])
    outcome = LlmAgentRuntime(llm=llm, workspace=_Workspace()).run_stage(
        "engineer", Stage.IMPLEMENT, _ctx()
    )
    assert outcome.result.tokens == 25
