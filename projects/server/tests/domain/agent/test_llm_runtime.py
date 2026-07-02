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
    runtime = LlmAgentRuntime(llm=llm, workspace_factory=lambda _p: ws)
    outcome = runtime.run_stage("engineer", Stage.IMPLEMENT, _ctx())
    assert ws.written["a.py"] == "x=1"
    assert outcome.result.passed is True
    assert "Implemented X." in outcome.result.summary
    assert any("write_file" in e.message for e in outcome.events)


def test_runtime_passes_role_model_alias_to_the_request():
    llm = FakeLLMAdapter([LLMResponse(content="done", stop_reason="end_turn")])
    LlmAgentRuntime(llm=llm, workspace_factory=lambda _p: _Workspace()).run_stage(
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
    runtime = LlmAgentRuntime(
        llm=FakeLLMAdapter(loop), workspace_factory=lambda _p: _Workspace(), max_iterations=3
    )
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
    outcome = LlmAgentRuntime(llm=llm, workspace_factory=lambda _p: _Workspace()).run_stage(
        "engineer", Stage.IMPLEMENT, _ctx()
    )
    assert outcome.result.tokens == 25


def test_runtime_builds_workspace_from_ctx_path():
    ws = _Workspace()
    seen: dict = {}

    def factory(path: str):
        seen["p"] = path
        return ws

    llm = FakeLLMAdapter([LLMResponse(content="done", stop_reason="end_turn")])
    LlmAgentRuntime(llm=llm, workspace_factory=factory).run_stage(
        "engineer", Stage.PLAN, _ctx(Stage.PLAN)
    )
    assert seen["p"] == "/ws"


def test_verify_fails_without_report():
    # VERIFY stage: LLM returns end_turn with no report tool → must fail (fail-safe)
    llm = FakeLLMAdapter([LLMResponse(content="looks good", stop_reason="end_turn")])
    outcome = LlmAgentRuntime(llm=llm, workspace_factory=lambda _p: _Workspace()).run_stage(
        "qa", Stage.VERIFY, _ctx(Stage.VERIFY)
    )
    assert outcome.result.passed is False


def test_report_tool_sets_verdict():
    # LLM returns a report tool call with passed=False → outcome must reflect it,
    # and the workspace must NOT have been asked to execute the report tool.
    ws = _Workspace()
    executed: list[str] = []
    original_bash = ws.bash

    def tracking_bash(cmd, timeout_s):
        executed.append(cmd)
        return original_bash(cmd, timeout_s)

    ws.bash = tracking_bash

    llm = FakeLLMAdapter([
        LLMResponse(
            tool_calls=[
                ToolCall(id="r", name="report", args={"passed": False, "summary": "tests failed"})
            ],
            stop_reason="tool_use",
        )
    ])
    outcome = LlmAgentRuntime(llm=llm, workspace_factory=lambda _p: ws).run_stage(
        "qa", Stage.VERIFY, _ctx(Stage.VERIFY)
    )
    assert outcome.result.passed is False
    assert outcome.result.summary == "tests failed"
    # report is a terminal signal — workspace must never execute it
    assert executed == []


def test_max_tokens_capped():
    # token_limit=200000 on the agent but the request must be capped at MAX_OUTPUT_TOKENS
    from domain.agent.runtime import MAX_OUTPUT_TOKENS
    llm = FakeLLMAdapter([LLMResponse(content="done", stop_reason="end_turn")])
    ctx = StageContext(
        run_id="r",
        role="engineer",
        stage=Stage.IMPLEMENT,
        workspace_path="/ws",
        work_item=WorkItemBrief(title="Big task"),
        agent=AgentDefinition(
            owner_id="o",
            team_id="t",
            role=AgentRole.BACKEND,
            model_alias="sonnet",
            token_limit=200000,
        ),
    )
    LlmAgentRuntime(llm=llm, workspace_factory=lambda _p: _Workspace()).run_stage(
        "engineer", Stage.IMPLEMENT, ctx
    )
    assert llm.requests[0].max_tokens == MAX_OUTPUT_TOKENS
    assert llm.requests[0].max_tokens == 16000
