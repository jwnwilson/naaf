from enum import Enum

from pydantic import BaseModel, Field

from domain.base import Entity


class WorkItemKind(str, Enum):
    EPIC = "epic"
    FEATURE = "feature"
    TASK = "task"


class WorkItemStatus(str, Enum):
    TO_DO = "to_do"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class AcceptanceCriterion(BaseModel):
    text: str
    done: bool = False


class WorkItem(Entity):
    owner_id: str
    project_id: str
    parent_id: str | None = None
    kind: WorkItemKind
    title: str
    body: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    status: WorkItemStatus = WorkItemStatus.TO_DO
