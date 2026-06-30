"""Domain ↔ contract mappers.

All functions are pure transforms — no I/O, no side effects.
Routes call these to convert between domain objects and the camelCase
contract shapes the UI consumes.
"""
from __future__ import annotations

from datetime import datetime

from domain.project import Project
from domain.team import AgentDefinition, Team
from domain.work_item import WorkItem

from interactors.api.contract import (
    AgentDefinitionOut,
    AgentDefinitionUpdateIn,
    ProjectCreateIn,
    ProjectOut,
    ProjectUpdateIn,
    TeamCreateIn,
    TeamOut,
    TeamUpdateIn,
    WorkItemCreateIn,
    WorkItemOut,
    WorkItemUpdateIn,
)
from interactors.api.schemas import (
    CreateProject,
    CreateTeam,
    CreateWorkItem,
    UpdateAgentDefinition,
    UpdateProject,
    UpdateTeam,
    UpdateWorkItem,
)


def _iso(dt: datetime | None) -> str:
    """Render a datetime as ISO-8601 string, or empty string if absent."""
    return dt.isoformat() if dt else ""


# ---------------------------------------------------------------------------
# WorkItem
# ---------------------------------------------------------------------------


def work_item_out(
    item: WorkItem,
    *,
    epic_id: str | None = None,
    feature_id: str | None = None,
) -> WorkItemOut:
    """Map a domain WorkItem to the camelCase contract response shape.

    epic_id and feature_id must be resolved by the route (they are not stored
    on the work item itself — they come from parent relationships).
    """
    return WorkItemOut(
        id=item.id,
        type=item.kind.value,
        title=item.title,
        status=item.status.value,
        priority=item.priority.value,
        assignedAgent=None,
        epicId=epic_id,
        featureId=feature_id,
        projectId=item.project_id,
        tokenUsageThisRun=None,
        tokenUsageAllRuns=None,
        tokenLimit=None,
        spec=item.body or None,
        attachments=[],
        createdAt=_iso(item.created_at),
        updatedAt=_iso(item.updated_at),
    )


def work_item_create_to_domain(body: WorkItemCreateIn) -> CreateWorkItem:
    """Map a WorkItemCreateIn to the domain CreateWorkItem schema.

    project_id and parent_id are NOT set here — the route injects them.
    """
    return CreateWorkItem(
        kind=body.type,
        title=body.title,
        body=body.spec or "",
        priority=body.priority,
    )


def work_item_update_to_domain(body: WorkItemUpdateIn) -> UpdateWorkItem:
    return UpdateWorkItem(
        title=body.title,
        body=body.spec,
        priority=body.priority,
    )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


def project_out(p: Project, *, item_count: int) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        repoUrl=p.repo_url or "",
        itemCount=item_count,
        createdAt=_iso(p.created_at),
        updatedAt=_iso(p.updated_at),
    )


def project_create_to_domain(body: ProjectCreateIn) -> CreateProject:
    return CreateProject(
        name=body.name,
        repo_url=body.repoUrl,
    )


def project_update_to_domain(body: ProjectUpdateIn) -> UpdateProject:
    return UpdateProject(
        name=body.name,
        repo_url=body.repoUrl,
    )


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------


def team_out(t: Team) -> TeamOut:
    return TeamOut(id=t.id, name=t.name)


def team_create_to_domain(body: TeamCreateIn) -> CreateTeam:
    return CreateTeam(name=body.name)


def team_update_to_domain(body: TeamUpdateIn) -> UpdateTeam:
    return UpdateTeam(name=body.name)


# ---------------------------------------------------------------------------
# AgentDefinition
# ---------------------------------------------------------------------------


def agent_definition_out(a: AgentDefinition) -> AgentDefinitionOut:
    return AgentDefinitionOut(
        id=a.id,
        teamId=a.team_id,
        role=a.role.value,
        model=a.model_alias,
        tokenLimit=a.token_limit,
        systemPrompt=a.persona_prompt or None,
        enabled=a.enabled,
    )


def agent_definition_update_to_domain(body: AgentDefinitionUpdateIn) -> UpdateAgentDefinition:
    return UpdateAgentDefinition(
        model_alias=body.model,
        persona_prompt=body.systemPrompt,
        token_limit=body.tokenLimit,
        enabled=body.enabled,
    )
