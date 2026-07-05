"""camelCase Pydantic models matching the UI OpenAPI contract.

*Out models: field names are already camelCase, so no Field(alias=...) is
needed and by_alias has no effect — the field names ARE the JSON keys.

*In models: received from the UI in camelCase; field names match JSON keys.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from domain.work_item import Priority, WorkItemKind, WorkItemStatus
from pydantic import BaseModel, ConfigDict, Field, field_validator


def iso(dt: datetime | None) -> str:
    """Render a persisted entity's timestamp as ISO-8601.

    Persisted rows always carry timestamps; a None here means an unsaved entity
    reached the contract layer, which we surface rather than emit "".
    """
    if dt is None:
        raise ValueError("timestamp is required for the contract")
    return dt.isoformat()

# ---------------------------------------------------------------------------
# WorkItem
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------


class AttachmentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    filename: str
    contentType: str
    size: int
    url: str
    createdAt: str


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
    repoUrl: str = ""


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


class AgentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role: str
    model: str
    status: str  # "running" | "idle"
    runId: str | None = None
    workItemId: str | None = None
    currentStage: str | None = None
    progress: float | None = None
    tokenUsage: int


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


class StageStateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stage: str
    status: str
    role: str | None = None
    startedAt: str | None = None
    endedAt: str | None = None


class GateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str
    stage: str


class RunOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    workItemId: str
    projectId: str
    autonomyLevel: str
    status: str
    currentStage: str | None = None
    stages: list[StageStateOut]
    pendingGate: GateOut | None = None
    createdAt: str
    updatedAt: str
    startedAt: str | None = None
    endedAt: str | None = None
    tokenUsage: int
    cost: float
    prUrl: str | None = None


class RunEventOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    runId: str
    seq: int
    stage: str | None = None
    role: str | None = None
    type: str
    payload: dict[str, Any]
    createdAt: str


class GateDecisionIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    decision: Literal["approve", "reject"]


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


class NotificationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    runId: str
    workItemId: str | None = None
    type: str  # NotificationType value
    title: str
    body: str
    read: bool
    createdAt: str
    updatedAt: str


# ---------------------------------------------------------------------------
# Messaging (work-item threads)
# ---------------------------------------------------------------------------


class ThreadOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str  # == workItemId
    workItemId: str
    projectId: str
    title: str
    status: str
    lastMessage: str | None = None
    messageCount: int = 0
    participants: list[str] = []
    createdAt: str


class ThreadParticipantOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str  # "user" | "agent"
    role: str
    name: str
    model: str | None = None
    status: str | None = None  # "running" | "idle" | None (user)


class ThreadDetailOut(ThreadOut):
    filesWritten: list[dict[str, Any]] = []
    participantDetails: list[ThreadParticipantOut] = []


class MessageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    threadId: str
    authorKind: str
    authorRole: str | None = None
    model: str | None = None
    kind: str
    content: str
    mentions: list[str] = []
    payload: dict[str, Any] = {}
    runId: str | None = None
    createdAt: str


class MessageCreate(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v


class AnswerIn(BaseModel):
    option: str

    @field_validator("option")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("option must not be empty")
        return v


# ---------------------------------------------------------------------------
# Activity events (agent event stream)
# ---------------------------------------------------------------------------


class AgentActivityEventOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    seq: int
    kind: str
    payload: dict = Field(default_factory=dict)
    createdAt: str


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TokenPointOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    day: str
    tokens: int


class ActivityEventOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    description: str
    agentId: str | None = None
    workItemId: str | None = None
    createdAt: str


class DashboardMetricsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    activeAgents: int
    totalSpend: float
    totalTokens: int
    projectCount: int
    workItemCount: int


class BudgetOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    used: float
    limit: float


# ---------------------------------------------------------------------------
# Secrets (owner-scoped, write-only)
# ---------------------------------------------------------------------------


class SecretOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    isSet: bool
    hint: str


class SecretSetIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    value: str

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("value must not be empty")
        return v
