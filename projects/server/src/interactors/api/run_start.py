"""Shared 'start a run' sequence — used by the runs route and by run-proposal
approval in the threads route.

Creates a queued Run, publishes the START message on the bus, and transitions
the work item to in_progress. Raises InvalidTransition if the item can't start.
"""

from typing import Any

from domain.runs.messages import AgentMessage, MessageType, recipient_key
from domain.runs.run import Run
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus


def start_run(uow: Any, bus: Any, owner_id: str, work_item_id: str) -> Run:
    work_item = uow.work_items.read(work_item_id)
    project = uow.projects.read(work_item.project_id)
    new_status = validate_transition(work_item.status, WorkItemStatus.IN_PROGRESS)
    run = uow.runs.create(Run(
        owner_id="",  # stamped by repo from required_filters
        work_item_id=work_item.id,
        project_id=project.id,
        autonomy_level=project.autonomy_level.value,
    ))
    bus.publish(AgentMessage(
        owner_id=owner_id,
        run_id=run.id,
        recipient=recipient_key(run.id, "lead"),
        role="lead",
        type=MessageType.START,
    ))
    uow.work_items.update(work_item.id, work_item.model_copy(update={"status": new_status}))
    return run
