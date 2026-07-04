"""Owner-scoped naaf domain operations exposed to Claude Code via MCP.

Each function takes an owner-scoped SqlUnitOfWork and thin-wraps existing code
(CtxOrchestrationTools, run_start, validate_transition, repos). The MCP server
(server.py) builds the uow from env per call and forwards to these; they are
tested directly against a real uow.
"""

from typing import Any

from adapters.agent.orchestration_tools import CtxOrchestrationTools
from adapters.bus.factory import build_message_bus
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus

from interactors.api.run_start import start_run as _start_run_seq


def _octools(uow: Any, owner_id: str, project_id: str) -> CtxOrchestrationTools:
    return CtxOrchestrationTools(
        work_items=uow.work_items,
        projects=uow.projects,
        messages=uow.messages,
        bus=build_message_bus(uow),
        owner_id=owner_id,
        project_id=project_id,
    )


def list_projects(uow: Any) -> list[dict]:
    return [{"id": p.id, "name": p.name} for p in uow.projects.read_multi(page_size=200).results]


def list_board(uow: Any, owner_id: str, project_id: str) -> str:
    return _octools(uow, owner_id, project_id).list_board()


def create_work_item(uow: Any, owner_id: str, project_id: str, kind: str, title: str,
                     spec: str = "", parent_id: str = "") -> str:
    return _octools(uow, owner_id, project_id).create_work_item(kind, title, spec, parent_id)


def update_work_item(uow: Any, owner_id: str, work_item_id: str, title: str = "",
                     spec: str = "", priority: str = "") -> str:
    return _octools(uow, owner_id, "").update_work_item(work_item_id, title, spec, priority)


def propose_run(uow: Any, owner_id: str, project_id: str, work_item_ids: list[str]) -> str:
    return _octools(uow, owner_id, project_id).propose_run(work_item_ids)


def get_work_item(uow: Any, work_item_id: str) -> dict:
    w = uow.work_items.read(work_item_id)
    return {
        "id": w.id, "kind": w.kind.value, "title": w.title, "body": w.body,
        "status": w.status.value, "priority": w.priority.value, "parentId": w.parent_id,
    }


def transition_status(uow: Any, work_item_id: str, status: str) -> dict:
    w = uow.work_items.read(work_item_id)
    new_status = validate_transition(w.status, WorkItemStatus(status))
    uow.work_items.update(work_item_id, w.model_copy(update={"status": new_status}))
    return {"id": work_item_id, "status": new_status.value}


def start_run(uow: Any, owner_id: str, work_item_id: str) -> dict:
    run = _start_run_seq(uow, build_message_bus(uow), owner_id, work_item_id)
    return {"runId": run.id, "workItemId": work_item_id, "status": run.status.value}


def list_runs(uow: Any, work_item_id: str = "") -> list[dict]:
    filters = {"work_item_id": work_item_id} if work_item_id else {}
    runs = uow.runs.read_multi(filters=filters, page_size=100).results
    return [
        {"id": r.id, "workItemId": r.work_item_id, "status": r.status.value, "prUrl": r.pr_url}
        for r in runs
    ]


def get_thread(uow: Any, thread_id: str) -> list[dict]:
    msgs = uow.messages.read_multi(
        filters={"thread_id": thread_id}, page_size=200, page_number=1, order_by="created_at"
    ).results
    return [
        {"authorKind": m.author_kind.value, "authorRole": m.author_role,
         "kind": m.kind.value, "content": m.content}
        for m in msgs
    ]
