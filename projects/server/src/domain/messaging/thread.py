from datetime import datetime

from pydantic import BaseModel

from domain.messaging.message import Message
from domain.work_item import WorkItem


class ThreadView(BaseModel):
    id: str  # == work_item_id
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


# ---------------------------------------------------------------------------
# Backward-compat shim — preserved so the old threads.py route can still
# import this name without crashing. Removed once threads.py is replaced
# in the Task 6 commit.
# ---------------------------------------------------------------------------

from domain.runs.run import Run  # noqa: E402


class _LegacyThreadView(BaseModel):
    id: str
    agent_id: str
    work_item_id: str
    created_at: datetime | None


THREAD_LEAD_ROLE = "lead"


def thread_from_run(run: Run) -> _LegacyThreadView:
    return _LegacyThreadView(
        id=run.id,
        agent_id=THREAD_LEAD_ROLE,
        work_item_id=run.work_item_id,
        created_at=run.created_at,
    )
