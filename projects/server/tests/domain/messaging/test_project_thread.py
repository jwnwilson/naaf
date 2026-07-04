from domain.messaging.message import AuthorKind, Message
from domain.messaging.thread import (
    is_project_thread,
    project_id_from_thread,
    project_thread_id,
    thread_from_project,
)
from domain.project import Project
from domain.runs.messages import project_chat_recipient


def test_project_thread_id_round_trips():
    tid = project_thread_id("p1")
    assert tid == "project:p1"
    assert is_project_thread(tid)
    assert not is_project_thread("w1")
    assert project_id_from_thread(tid) == "p1"


def test_project_chat_recipient_uses_proj_namespace():
    assert project_chat_recipient("p1", "lead") == "proj:p1:lead"


def test_thread_from_project_projects_messages():
    project = Project(owner_id="u1", name="naaf", repo_url="https://x/y")
    msgs = [
        Message(owner_id="u1", thread_id=project_thread_id(project.id), content="hi",
                author_kind=AuthorKind.USER),
        Message(owner_id="u1", thread_id=project_thread_id(project.id), content="planning",
                author_kind=AuthorKind.AGENT, author_role="lead"),
    ]
    view = thread_from_project(project, msgs)
    assert view.id == project_thread_id(project.id)
    assert view.title == "naaf"
    assert view.message_count == 2
    assert view.last_message == "planning"
