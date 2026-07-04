from adapters.agent.chat.orchestrator_echo import EchoOrchestrator
from adapters.database.uow import SqlUnitOfWork
from domain.messaging.message import AuthorKind
from domain.messaging.thread import project_thread_id
from domain.project import Project
from domain.runs.messages import AgentMessage, MessageType, project_chat_recipient
from domain.work_item import WorkItemKind
from interactors.worker.handlers import HandlerContext, handle_chat


class FakeBus:
    def __init__(self):
        self.published = []

    def publish(self, msg):
        self.published.append(msg)


def test_project_chat_runs_orchestrator_and_posts_lead_reply(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.create(Project(owner_id="", name="naaf"))
        ctx = HandlerContext(
            runs=uow.runs, run_events=uow.run_events, work_items=uow.work_items,
            notifications=None, bus=FakeBus(), runtime=None,
            projects=uow.projects, messages=uow.messages,
            lead_orchestrator=EchoOrchestrator(),
        )
        tid = project_thread_id(project.id)
        msg = AgentMessage(
            owner_id="u1", run_id="", recipient=project_chat_recipient(project.id, "lead"),
            role="lead", type=MessageType.CHAT,
            payload={"thread_id": tid, "project_id": project.id, "depth": 0},
        )

        handle_chat(msg, ctx)

        items = uow.work_items.read_multi(filters={"project_id": project.id}).results
        assert any(w.kind is WorkItemKind.EPIC for w in items)
        msgs = uow.messages.read_multi(filters={"thread_id": tid}).results
        assert any(m.author_role == "lead" and m.author_kind is AuthorKind.AGENT for m in msgs)
