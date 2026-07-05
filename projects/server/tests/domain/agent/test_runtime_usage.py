from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.llm import LLMResponse, Usage
from domain.agent.runtime import LlmAgentRuntime
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


class _FakeLLM:
    """Returns one non-tool response with scripted usage, ending the stage."""

    def __init__(self):
        self._n = 0

    def complete(self, request):
        self._n += 1
        return LLMResponse(
            content="done", tool_calls=[], stop_reason="end_turn",
            usage=Usage(input_tokens=120, output_tokens=30),
        )


class _NoWorkspace:
    pass


def _ctx():
    return StageContext(
        run_id="r1", role="engineer", stage=Stage.IMPLEMENT, workspace_path="/tmp/x",
        work_item=WorkItemBrief(title="T"),
        agent=AgentDefinition(owner_id="o", team_id="t", role=AgentRole.BACKEND, model_alias="sonnet"),
    )


def test_run_stage_captures_input_output_split_and_model():
    rt = LlmAgentRuntime(_FakeLLM(), workspace_factory=lambda _p: _NoWorkspace())
    outcome = rt.run_stage("engineer", Stage.IMPLEMENT, _ctx())
    res = outcome.result
    assert res.input_tokens == 120
    assert res.output_tokens == 30
    assert res.tokens == 150            # combined stays
    assert res.model == "sonnet"        # the request alias


def test_fake_runtime_sets_split_and_model():
    from adapters.agent.runtime.fake import FakeAgentRuntime
    outcome = FakeAgentRuntime().run_stage("engineer", Stage.IMPLEMENT, _ctx())
    res = outcome.result
    assert res.input_tokens > 0 and res.output_tokens > 0
    assert res.input_tokens + res.output_tokens == res.tokens
    assert res.model == "sonnet"
