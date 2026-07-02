from adapters.agent.runtime.fake import TOKENS_PER_STEP, FakeAgentRuntime
from domain.agent.context import StageContext, WorkItemBrief
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


def _ctx(stage: Stage, verify_attempts: int = 0) -> StageContext:
    return StageContext(
        run_id="r",
        role="qa",
        stage=stage,
        workspace_path="/ws",
        work_item=WorkItemBrief(title="t"),
        agent=AgentDefinition(owner_id="o", team_id="t", role=AgentRole.QA),
        verify_attempts=verify_attempts,
    )


def test_fake_passes_by_default_and_emits_events():
    rt = FakeAgentRuntime()
    out = rt.run_stage("lead", Stage.PLAN, _ctx(Stage.PLAN))
    assert out.result.passed is True
    assert len(out.events) >= 1
    assert all(e.message for e in out.events)


def test_fake_verify_fails_then_passes():
    rt = FakeAgentRuntime(fail_verify_times=1)
    first = rt.run_stage("qa", Stage.VERIFY, _ctx(Stage.VERIFY, verify_attempts=0))
    second = rt.run_stage("qa", Stage.VERIFY, _ctx(Stage.VERIFY, verify_attempts=1))
    assert first.result.passed is False
    assert second.result.passed is True


def test_run_stage_reports_tokens_proportional_to_steps():
    rt = FakeAgentRuntime()
    outcome = rt.run_stage("lead", Stage.PLAN, _ctx(Stage.PLAN))
    assert outcome.result.tokens == TOKENS_PER_STEP * len(outcome.events)
    assert outcome.result.tokens > 0
