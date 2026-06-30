"""camelCase Pydantic models matching the UI OpenAPI contract.

*Out models: serialise with model_dump(by_alias=True) — field names ARE the
JSON keys (already camelCase), so by_alias=True works without explicit aliases.

*In models: received from the UI in camelCase; field names match JSON keys.
"""
from __future__ import annotations

from typing import Any

from domain.work_item import Priority, WorkItemKind, WorkItemStatus
from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# WorkItem
# ---------------------------------------------------------------------------


class WorkItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str  # WorkItemKind value
    title: str
    status: str  # WorkItemStatus value
    priority: str  # Priority value
    assignedAgent: Any | None = None
    epicId: str | None = None
    featureId: str | None = None
    projectId: str
    tokenUsageThisRun: int | None = None
    tokenUsageAllRuns: int | None = None
    tokenLimit: int | None = None
    spec: str | None = None
    attachments: list[Any] | None = None
    createdAt: str
    updatedAt: str


class WorkItemCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: WorkItemKind
    title: str
    status: WorkItemStatus = WorkItemStatus.TODO
    priority: Priority = Priority.MEDIUM
    epicId: str | None = None
    featureId: str | None = None
    spec: str | None = None


class WorkItemUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    priority: Priority | None = None
    epicId: str | None = None
    featureId: str | None = None
    assignedAgentId: str | None = None
    tokenLimit: int | None = None
    spec: str | None = None


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class ProjectOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    repoUrl: str
    itemCount: int
    createdAt: str
    updatedAt: str


class ProjectCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    repoUrl: str


class ProjectUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    repoUrl: str | None = None


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------


class TeamOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str


class TeamCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str


class TeamUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None


# ---------------------------------------------------------------------------
# AgentDefinition
# ---------------------------------------------------------------------------


class AgentDefinitionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    teamId: str
    role: str
    model: str
    tokenLimit: int
    systemPrompt: str | None = None
    enabled: bool


class AgentDefinitionUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model: str | None = None
    tokenLimit: int | None = None
    systemPrompt: str | None = None
    enabled: bool | None = None
