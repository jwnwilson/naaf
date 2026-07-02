from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.prompts import stage_instruction, system_prompt
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


def _ctx(stage, persona="You are a senior engineer."):
    return StageContext(
        run_id="r", role="engineer", stage=stage, workspace_path="/ws",
        work_item=WorkItemBrief(title="Add feature", body="details",
                                acceptance_criteria=["it works"]),
        agent=AgentDefinition(owner_id="o", team_id="t", role=AgentRole.BACKEND,
                              persona_prompt=persona),
    )


def test_system_prompt_includes_persona():
    assert "senior engineer" in system_prompt(_ctx(Stage.IMPLEMENT))


def test_instruction_is_stage_specific():
    assert "plan.md" in stage_instruction(_ctx(Stage.PLAN)).lower()
    assert "test" in stage_instruction(_ctx(Stage.VERIFY)).lower()


def test_instruction_includes_acceptance_criteria():
    assert "it works" in stage_instruction(_ctx(Stage.IMPLEMENT))
