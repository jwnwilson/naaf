from domain.project import AutonomyLevel
from domain.team import AgentRole
from domain.work_item import AcceptanceCriterion, Priority, WorkItemStatus
from pydantic import BaseModel


class UpdateProject(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel | None = None


class UpdateWorkItem(BaseModel):
    title: str | None = None
    body: str | None = None
    acceptance_criteria: list[AcceptanceCriterion] | None = None
    priority: Priority | None = None
    # NOTE: status is intentionally absent — status changes go through the
    # transition route so the state machine is always enforced.


class TransitionRequest(BaseModel):
    status: WorkItemStatus


class CreateTeam(BaseModel):
    name: str


class UpdateTeam(BaseModel):
    name: str | None = None


class CreateAgentDefinition(BaseModel):
    team_id: str
    role: AgentRole
    persona_prompt: str = ""
    model_alias: str = ""
    runtime_adapter: str = "claude_code"
    memory_scope: str = "project"
    capability_grants: list[str] = []


class UpdateAgentDefinition(BaseModel):
    role: AgentRole | None = None
    persona_prompt: str | None = None
    model_alias: str | None = None
    runtime_adapter: str | None = None
    memory_scope: str | None = None
    capability_grants: list[str] | None = None
    token_limit: int | None = None
    enabled: bool | None = None
