from domain.agent.context import StageContext, WorkItemBrief
from domain.agent.prompts import stage_instruction
from domain.runs.run import Stage
from domain.team import AgentDefinition, AgentRole


def _ctx(attachments):
    return StageContext(
        run_id="r1", role="engineer", stage=Stage.IMPLEMENT, workspace_path="/tmp/x",
        work_item=WorkItemBrief(title="T", body="B", attachments=attachments),
        agent=AgentDefinition(owner_id="o", team_id="", role=AgentRole.BACKEND),
    )


def test_instruction_lists_attachments_when_present():
    text = stage_instruction(_ctx(["mockup.png", "notes.md"]))
    assert "## Attachments" in text
    assert ".naaf/attachments/" in text
    assert "mockup.png" in text and "notes.md" in text


def test_instruction_omits_section_when_no_attachments():
    text = stage_instruction(_ctx([]))
    assert "## Attachments" not in text
