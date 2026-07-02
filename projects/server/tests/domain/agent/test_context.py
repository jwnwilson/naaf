from domain.agent.context import StageContext, WorkItemBrief
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


def test_stage_context_holds_the_run_inputs():
    agent = AgentDefinition(owner_id="o", team_id="t", role=AgentRole.BACKEND,
                            model_alias="sonnet")
    ctx = StageContext(
        run_id="r1", role="engineer", stage=Stage.IMPLEMENT, workspace_path="/tmp/ws",
        work_item=WorkItemBrief(title="Add X", acceptance_criteria=["does X"]),
        agent=agent,
    )
    assert ctx.stage is Stage.IMPLEMENT
    assert ctx.agent.model_alias == "sonnet"
    assert ctx.verify_attempts == 0
    assert ctx.artifacts == {}
