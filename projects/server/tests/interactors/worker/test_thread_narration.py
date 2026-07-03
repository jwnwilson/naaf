"""Test that the run pipeline narrates lifecycle events into the work-item thread."""
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
        p = uow.projects.create(Project(owner_id="", name="P", autonomy_level="full_auto"))
        wi = uow.work_items.create(WorkItem(
            owner_id="", project_id=p.id, kind=WorkItemKind.TASK, title="T", status="todo"
        ))
        run = uow.runs.create(
            Run(owner_id="", work_item_id=wi.id, project_id=p.id, autonomy_level="full_auto")
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


def test_run_narrates_lifecycle_into_thread(session_factory):
    rt = FakeAgentRuntime()
    wid, run_id = _seed(session_factory)
    _start(session_factory, run_id)
    _drain(session_factory, rt)

    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        msgs = uow.messages.read_multi(
            filters={"thread_id": wid}, order_by="created_at"
        ).results
        kinds_roles = [(m.author_kind.value, m.author_role, m.kind.value) for m in msgs]
        # lead announces the start with planning signal
        start_msgs = [m for m in msgs if m.author_role == "lead" and m.kind.value == "text"
                      and "Planning now." in m.content]
        assert start_msgs, "expected a start narration containing 'Planning now.'"
        # at least one stage result was narrated by a non-lead role (e.g. engineer/qa)
        assert any(r in {"engineer", "qa"} for (_ak, r, _k) in kinds_roles)
        # stage narration lines include summary segment (": " followed by summary or "(no summary)")
        stage_narrations = [
            m for m in msgs
            if m.author_kind.value == "agent" and m.kind.value == "text"
            and ": " in m.content and m.author_role in {"engineer", "qa", "lead", "curator"}
            and ("passed" in m.content or "failed" in m.content)
        ]
        assert stage_narrations, "expected stage narration messages with summary content"
        for m in stage_narrations:
            # must contain ": <summary>" or ": (no summary)"
            assert ": " in m.content, f"stage narration missing summary segment: {m.content!r}"
        # a run-finished line exists with status value
        finished_msgs = [m for m in msgs if "Run finished:" in m.content]
        assert finished_msgs, "expected a 'Run finished: <status>.' narration"
        assert any(
            any(status in m.content for status in ("succeeded", "failed", "cancelled"))
            for m in finished_msgs
        ), f"run-finished narration missing status value: {[m.content for m in finished_msgs]}"
        # every narrated message links back to the run and is thread-scoped
        assert all(m.thread_id == wid and m.run_id is not None for m in msgs)
