from datetime import datetime

from domain.messaging.message import AuthorKind, Message
from domain.messaging.thread import thread_from_work_item
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus


def _item() -> WorkItem:
    return WorkItem(
        id="wi1", owner_id="o", project_id="p1", kind=WorkItemKind.TASK,
        title="Implement OAuth token refresh flow", status=WorkItemStatus.IN_PROGRESS,
        created_at=datetime(2026, 7, 3, 10, 38),
    )


def test_thread_id_is_work_item_id_and_carries_title_status():
    view = thread_from_work_item(_item(), [])
    assert view.id == "wi1"
    assert view.work_item_id == "wi1"
    assert view.title == "Implement OAuth token refresh flow"
    assert view.status == "in_progress"
    assert view.message_count == 0
    assert view.last_message is None
    assert view.participants == []


def test_participants_are_distinct_senders_and_last_message_is_newest():
    msgs = [
        Message(owner_id="o", thread_id="wi1", content="assigning", author_kind=AuthorKind.AGENT, author_role="lead"),
        Message(owner_id="o", thread_id="wi1", content="on it", author_kind=AuthorKind.AGENT, author_role="backend"),
        Message(owner_id="o", thread_id="wi1", content="use option B"),  # user
    ]
    view = thread_from_work_item(_item(), msgs)
    assert view.participants == ["lead", "backend", "user"]
    assert view.last_message == "use option B"
    assert view.message_count == 3
