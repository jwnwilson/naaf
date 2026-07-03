"""Test that gates emit a resolvable question message into the work-item thread."""
from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.factory import build_message_bus
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run
from domain.work_item import WorkItem, WorkItemKind
from interactors.worker.subscription_runner import run_subscription


def _seed(session_factory):
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        p = uow.projects.create(Project(owner_id="", name="P", autonomy_level="gated_all"))
        wi = uow.work_items.create(WorkItem(
            owner_id="", project_id=p.id, kind=WorkItemKind.TASK, title="T", status="todo"
        ))
        run = uow.runs.create(
            Run(owner_id="", work_item_id=wi.id, project_id=p.id, autonomy_level="gated_all")
        )
    return wi.id, run.id


def _start(session_factory, run_id):
    uow = SqlUnitOfWork(session_factory)
    with uow.transaction():
        build_message_bus(uow).publish(
            AgentMessage(
                owner_id="u1", run_id=run_id,
                recipient=recipient_key(run_id, "lead"),
                role="lead", type=MessageType.START,
            ),
        )


def _drain(session_factory, runtime):
    while run_subscription("agent-bus", session_factory, runtime):
        pass


def test_gate_emits_question_and_resolution_stamps_option(session_factory):
    rt = FakeAgentRuntime()
    wid, run_id = _seed(session_factory)
    _start(session_factory, run_id)
    _drain(session_factory, rt)

    # Check the question message at the gate
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        qs = [
            m for m in uow.messages.read_multi(
                filters={"thread_id": wid}, order_by="created_at"
            ).results
            if m.kind.value == "question"
        ]
        assert len(qs) == 1
        q = qs[0]
        assert q.author_role == "lead"
        assert q.payload["run_id"] == run_id
        assert q.payload["gate_kind"] == "plan"
        assert q.payload["resolved_option"] is None
        assert [o["id"] for o in q.payload["options"]] == ["approve", "reject"]

    # Approve the gate
    uow2 = SqlUnitOfWork(session_factory)
    with uow2.transaction():
        build_message_bus(uow2).publish(
            AgentMessage(
                owner_id="u1", run_id=run_id,
                recipient=recipient_key(run_id, "lead"),
                role="lead", type=MessageType.GATE_RESOLVED,
                payload={"decision": "approve"},
            ),
        )
    _drain(session_factory, rt)

    # Check that resolved_option is stamped
    uow3 = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow3.transaction():
        q2 = uow3.messages.read(q.id)
        assert q2.payload["resolved_option"] == "approve"
