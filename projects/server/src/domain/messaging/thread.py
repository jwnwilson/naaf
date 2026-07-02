from datetime import datetime

from pydantic import BaseModel

from domain.runs.run import Run
from domain.team import AgentRole

THREAD_LEAD_ROLE = AgentRole.LEAD.value  # "lead"


class ThreadView(BaseModel):
    id: str
    agent_id: str
    work_item_id: str
    created_at: datetime | None


def thread_from_run(run: Run) -> ThreadView:
    return ThreadView(
        id=run.id,
        agent_id=THREAD_LEAD_ROLE,
        work_item_id=run.work_item_id,
        created_at=run.created_at,
    )
