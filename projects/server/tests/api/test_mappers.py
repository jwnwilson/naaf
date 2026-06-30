from domain.team import AgentDefinition, AgentRole
from domain.work_item import Priority, WorkItem, WorkItemKind, WorkItemStatus
from interactors.api.mappers import agent_definition_out, work_item_out


def test_work_item_out_renames_and_camelcases():
    item = WorkItem(owner_id="u1", project_id="p1", kind=WorkItemKind.TASK, title="Auth",
                    body="# spec", status=WorkItemStatus.IN_PROGRESS, priority=Priority.HIGH)
    out = work_item_out(item).model_dump(by_alias=True)
    assert out["type"] == "task"
    assert out["spec"] == "# spec"
    assert out["projectId"] == "p1"
    assert out["status"] == "in_progress"
    assert out["priority"] == "high"
    assert out["assignedAgent"] is None
    assert "kind" not in out and "owner_id" not in out


def test_agent_definition_out_renames_model_and_prompt():
    a = AgentDefinition(owner_id="u1", team_id="t1", role=AgentRole.LEAD,
                        model_alias="claude-opus-4", persona_prompt="be helpful")
    out = agent_definition_out(a).model_dump(by_alias=True)
    assert out["model"] == "claude-opus-4"
    assert out["systemPrompt"] == "be helpful"
    assert out["enabled"] is True
    assert out["tokenLimit"] == 200000
