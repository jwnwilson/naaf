from enum import StrEnum

from domain.base import Entity


class AgentRole(StrEnum):
    LEAD = "lead"
    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    QA = "qa"
    DEVOPS = "devops"
    CUSTOM = "custom"


class Team(Entity):
    owner_id: str
    name: str


class AgentDefinition(Entity):
    owner_id: str
    team_id: str
    role: AgentRole
    persona_prompt: str = ""
    model_alias: str = ""
    runtime_adapter: str = "claude_code"
    memory_scope: str = "project"
