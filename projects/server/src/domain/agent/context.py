from pydantic import BaseModel, Field

from domain.runs.run import Stage
from domain.team import AgentDefinition


class WorkItemBrief(BaseModel):
    title: str
    body: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)


class StageContext(BaseModel):
    run_id: str
    role: str
    stage: Stage
    workspace_path: str
    work_item: WorkItemBrief
    agent: AgentDefinition
    verify_attempts: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
