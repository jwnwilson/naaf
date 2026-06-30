from enum import StrEnum

from pydantic import BaseModel, Field

from domain.base import Entity


class WorkItemKind(StrEnum):
    EPIC = "epic"
    FEATURE = "feature"
    TASK = "task"


class WorkItemStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"


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
    status: WorkItemStatus = WorkItemStatus.TODO
