from datetime import datetime

from pydantic import BaseModel

from domain.messaging.message import Message
from domain.project import Project
from domain.work_item import WorkItem

# A project-level thread (the "chat with lead" conversation) is keyed by a
# namespaced thread id so it can share the messages store + routes with
# work-item threads without a schema change.
PROJECT_THREAD_PREFIX = "project:"


def project_thread_id(project_id: str) -> str:
    return f"{PROJECT_THREAD_PREFIX}{project_id}"


def is_project_thread(thread_id: str) -> bool:
    return thread_id.startswith(PROJECT_THREAD_PREFIX)


def project_id_from_thread(thread_id: str) -> str:
    return thread_id[len(PROJECT_THREAD_PREFIX):]


class ThreadView(BaseModel):
    id: str  # work_item_id, or "project:<id>" for a project-level thread
    work_item_id: str
    title: str
    status: str
    participants: list[str]
    last_message: str | None
    message_count: int
    created_at: datetime | None


def _participants(messages: list[Message]) -> list[str]:
    seen: list[str] = []
    for m in messages:
        label = m.author_role if m.author_role else "user"
        if label not in seen:
            seen.append(label)
    return seen


def thread_from_work_item(item: WorkItem, messages: list[Message]) -> ThreadView:
    ordered = sorted(messages, key=lambda m: m.created_at or datetime.min)
    return ThreadView(
        id=item.id,
        work_item_id=item.id,
        title=item.title,
        status=item.status.value,
        participants=_participants(ordered),
        last_message=ordered[-1].content if ordered else None,
        message_count=len(ordered),
        created_at=item.created_at,
    )


def thread_from_project(project: Project, messages: list[Message]) -> ThreadView:
    """The project-level 'chat with lead' thread — not tied to a work item."""
    ordered = sorted(messages, key=lambda m: m.created_at or datetime.min)
    return ThreadView(
        id=project_thread_id(project.id),
        work_item_id="",
        title=project.name,
        status="project",
        participants=_participants(ordered),
        last_message=ordered[-1].content if ordered else None,
        message_count=len(ordered),
        created_at=project.created_at,
    )
