"""Adapter implementing the ``OrchestrationTools`` port over the worker context.

Domain validation (``validate_hierarchy``) stays pure; this adapter does the I/O
through the owner-scoped repositories the chat handler already holds.
"""

from typing import Any

from domain.errors import InvalidHierarchy
from domain.hierarchy import validate_hierarchy
from domain.messaging.message import AuthorKind, Message, MessageKind
from domain.messaging.question import run_proposal_payload
from domain.messaging.thread import project_thread_id
from domain.work_item import Priority, WorkItem, WorkItemKind, WorkItemStatus


class CtxOrchestrationTools:
    def __init__(self, *, work_items: Any, projects: Any, messages: Any, bus: Any,
                 owner_id: str, project_id: str) -> None:
        self._work_items = work_items
        self._projects = projects
        self._messages = messages
        self._bus = bus
        self._owner_id = owner_id
        self._project_id = project_id

    def list_board(self) -> str:
        items = self._work_items.read_multi(
            filters={"project_id": self._project_id}, page_size=500, page_number=1
        ).results
        if not items:
            return "(no work items yet)"
        lines = [
            f"- {w.kind.value} '{w.title}' id={w.id}"
            + (f" parent={w.parent_id}" if w.parent_id else "")
            for w in items
        ]
        return "\n".join(lines)

    def create_work_item(self, kind: str, title: str, spec: str = "", parent_id: str = "") -> str:
        child_kind = WorkItemKind(kind)
        parent = self._work_items.read(parent_id) if parent_id else None
        validate_hierarchy(child_kind, parent)
        if parent is not None and parent.project_id != self._project_id:
            raise InvalidHierarchy("parent must belong to the same project")
        saved = self._work_items.create(
            WorkItem(
                owner_id="",
                project_id=self._project_id,
                parent_id=parent_id or None,
                kind=child_kind,
                title=title,
                body=spec,
                priority=Priority.MEDIUM,
                status=WorkItemStatus.TODO,
            )
        )
        return f"created {kind} '{title}' id={saved.id}"

    def update_work_item(
        self, work_item_id: str, title: str = "", spec: str = "", priority: str = ""
    ) -> str:
        current = self._work_items.read(work_item_id)
        updates: dict[str, Any] = {}
        if title:
            updates["title"] = title
        if spec:
            updates["body"] = spec
        if priority:
            updates["priority"] = Priority(priority)
        if updates:
            self._work_items.update(work_item_id, current.model_copy(update=updates))
        return f"updated {work_item_id}"

    def propose_run(self, work_item_ids: list[str]) -> str:
        self._messages.create(
            Message(
                owner_id="",
                thread_id=project_thread_id(self._project_id),
                author_kind=AuthorKind.AGENT,
                author_role="lead",
                kind=MessageKind.QUESTION,
                content="Start development on these items?",
                payload=run_proposal_payload(work_item_ids),
            )
        )
        return f"proposed a run on {len(work_item_ids)} item(s)"
