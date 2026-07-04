from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.live_agents import LiveAgent, build_live_agents
from fastapi import APIRouter, Depends

from interactors.api.contract import AgentOut
from interactors.api.deps import get_uow

router = APIRouter(prefix="/agents", tags=["agents"])


def _agent_out(a: LiveAgent) -> AgentOut:
    return AgentOut(
        role=a.role.value,
        model=a.model,
        status=a.status,
        runId=a.run_id,
        workItemId=a.work_item_id,
        currentStage=a.current_stage.value if a.current_stage else None,
        progress=a.progress,
        tokenUsage=a.token_usage,
    )


@router.get("", response_model=Envelope[list[AgentOut]])
def list_agents(uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    definitions = uow.agent_definitions.read_multi(
        filters={"enabled": True}, page_size=100
    ).results
    active_runs = uow.runs.read_multi(
        filters={"status__in": ["running", "awaiting_gate"]}, page_size=100
    ).results
    return ok([_agent_out(a) for a in build_live_agents(definitions, active_runs)])
