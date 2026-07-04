from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from domain.messaging.message import Message
from domain.project import Project
from domain.work_item import WorkItem

# Human display names for the fixed team roles. Unknown roles fall back to a
# title-cased version of the raw role string.
ROLE_LABELS: dict[str, str] = {
    "user": "You",
    "lead": "Lead Agent",
    "architect": "Architect",
    "backend": "Backend Engineer",
    "frontend": "Frontend Engineer",
    "qa": "QA Engineer",
    "devops": "DevOps Engineer",
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.replace("_", " ").title())

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


class ThreadParticipant(BaseModel):
    """A distinct sender in a thread, enriched for the D3 participants rail."""

    kind: Literal["user", "agent"]
    role: str  # "user", or an agent role: lead/backend/frontend/qa/architect/devops
    name: str  # human display name (e.g. "Lead Agent", "You")
    model: str | None = None  # latest model seen for this role; None for the user
    status: Literal["running", "idle"] | None = None  # None for the user


class ThreadView(BaseModel):
    id: str  # work_item_id, or "project:<id>" for a project-level thread
    work_item_id: str
    project_id: str
    title: str
    status: str
    participants: list[str]
    participant_details: list[ThreadParticipant]
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


def _participant_details(
    messages: list[Message], active_roles: set[str]
) -> list[ThreadParticipant]:
    """Distinct senders, first-seen order, enriched with name/model/status.

    `messages` is expected pre-sorted oldest-first, so the last model seen for a
    role wins. `active_roles` are the roles currently running (agents only).
    """
    order: list[str] = []
    latest_model: dict[str, str | None] = {}
    for m in messages:
        role = m.author_role or "user"
        if role not in order:
            order.append(role)
        if m.model_alias is not None:
            latest_model[role] = m.model_alias

    details: list[ThreadParticipant] = []
    for role in order:
        is_user = role == "user"
        details.append(
            ThreadParticipant(
                kind="user" if is_user else "agent",
                role=role,
                name=role_label(role),
                model=None if is_user else latest_model.get(role),
                status=None if is_user else ("running" if role in active_roles else "idle"),
            )
        )
    return details


def thread_from_work_item(
    item: WorkItem, messages: list[Message], active_roles: set[str] | None = None
) -> ThreadView:
    ordered = sorted(messages, key=lambda m: m.created_at or datetime.min)
    return ThreadView(
        id=item.id,
        work_item_id=item.id,
        project_id=item.project_id,
        title=item.title,
        status=item.status.value,
        participants=_participants(ordered),
        participant_details=_participant_details(ordered, active_roles or set()),
        last_message=ordered[-1].content if ordered else None,
        message_count=len(ordered),
        created_at=item.created_at,
    )


def thread_from_project(
    project: Project, messages: list[Message], active_roles: set[str] | None = None
) -> ThreadView:
    """The project-level 'chat with lead' thread — not tied to a work item."""
    ordered = sorted(messages, key=lambda m: m.created_at or datetime.min)
    return ThreadView(
        id=project_thread_id(project.id),
        work_item_id="",
        project_id=project.id,
        title=project.name,
        status="project",
        participants=_participants(ordered),
        participant_details=_participant_details(ordered, active_roles or set()),
        last_message=ordered[-1].content if ordered else None,
        message_count=len(ordered),
        created_at=project.created_at,
    )
