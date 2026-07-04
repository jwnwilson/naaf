from datetime import datetime

from domain.messaging.message import AuthorKind, Message
from domain.messaging.thread import thread_from_work_item
from domain.work_item import WorkItem, WorkItemKind, WorkItemStatus


def _msg(role: str | None, content: str, *, model: str | None = None, minute: int = 0) -> Message:
    return Message(
        owner_id="o",
        thread_id="wi1",
        content=content,
        author_kind=AuthorKind.USER if role is None else AuthorKind.AGENT,
        author_role=role,
        model_alias=model,
        created_at=datetime(2026, 7, 3, 10, 38 + minute),
    )


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
        Message(
            owner_id="o", thread_id="wi1", content="assigning",
            author_kind=AuthorKind.AGENT, author_role="lead",
        ),
        Message(
            owner_id="o", thread_id="wi1", content="on it",
            author_kind=AuthorKind.AGENT, author_role="backend",
        ),
        Message(owner_id="o", thread_id="wi1", content="use option B"),  # user
    ]
    view = thread_from_work_item(_item(), msgs)
    assert view.participants == ["lead", "backend", "user"]
    assert view.last_message == "use option B"
    assert view.message_count == 3


def test_participant_details_carry_display_name_kind_and_role():
    msgs = [
        _msg("lead", "assigning", minute=0),
        _msg("backend", "on it", model="claude-opus-4", minute=1),
        _msg(None, "use option B", minute=2),
    ]
    details = thread_from_work_item(_item(), msgs).participant_details
    by_role = {p.role: p for p in details}
    assert by_role["lead"].kind == "agent"
    assert by_role["lead"].name == "Lead Agent"
    assert by_role["backend"].kind == "agent"
    assert by_role["backend"].name == "Backend Engineer"
    assert by_role["user"].kind == "user"
    assert by_role["user"].name == "You"
    # ordering matches first-seen order, same as `participants`
    assert [p.role for p in details] == ["lead", "backend", "user"]


def test_participant_model_is_the_latest_seen_for_that_role():
    msgs = [
        _msg("backend", "first", model="claude-sonnet-4", minute=0),
        _msg("backend", "second", model="claude-opus-4", minute=1),
    ]
    details = thread_from_work_item(_item(), msgs).participant_details
    assert details[0].model == "claude-opus-4"


def test_user_participant_has_no_model_or_status():
    details = thread_from_work_item(_item(), [_msg(None, "hi")]).participant_details
    user = details[0]
    assert user.model is None
    assert user.status is None


def test_agent_status_is_running_when_role_is_active_else_idle():
    msgs = [_msg("lead", "assigning", minute=0), _msg("backend", "on it", minute=1)]
    details = thread_from_work_item(
        _item(), msgs, active_roles={"backend"}
    ).participant_details
    by_role = {p.role: p for p in details}
    assert by_role["backend"].status == "running"
    assert by_role["lead"].status == "idle"


def test_thread_from_work_item_carries_project_id():
    view = thread_from_work_item(_item(), [])
    assert view.project_id == "p1"
