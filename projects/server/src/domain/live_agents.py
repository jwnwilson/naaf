from datetime import datetime

from pydantic import BaseModel

from domain.runs.run import Run, Stage, StageStatus
from domain.team import AgentDefinition, AgentRole

# Pipeline dispatch stage-role -> roster AgentRole.
STAGE_ROLE_TO_AGENT_ROLE: dict[str, AgentRole] = {
    "lead": AgentRole.LEAD,
    "engineer": AgentRole.BACKEND,
    "qa": AgentRole.QA,
}

# Fallback: which stage-role runs each stage (when a StageState carries no role).
STAGE_TO_STAGE_ROLE: dict[Stage, str] = {
    Stage.PLAN: "lead",
    Stage.PROVISION: "lead",
    Stage.PR: "lead",
    Stage.LEARN: "lead",
    Stage.IMPLEMENT: "engineer",
    Stage.VERIFY: "qa",
}

# Fixed display order for roster rows.
ROLE_ORDER: list[AgentRole] = [
    AgentRole.LEAD,
    AgentRole.ARCHITECT,
    AgentRole.BACKEND,
    AgentRole.FRONTEND,
    AgentRole.QA,
    AgentRole.DEVOPS,
]

_TOTAL_STAGES = len(list(Stage))  # 6


class LiveAgent(BaseModel):
    role: AgentRole
    model: str
    status: str = "idle"  # "running" | "idle"
    run_id: str | None = None
    work_item_id: str | None = None
    current_stage: Stage | None = None
    progress: float | None = None
    token_usage: int = 0


def _current_agent_role(run: Run) -> AgentRole | None:
    if run.current_stage is None:
        return None
    stage_role: str | None = None
    for s in run.stages:
        if s.stage == run.current_stage and s.status == StageStatus.RUNNING:
            stage_role = s.role
            break
    if stage_role is None:
        stage_role = STAGE_TO_STAGE_ROLE.get(run.current_stage)
    if stage_role is None:
        return None
    return STAGE_ROLE_TO_AGENT_ROLE.get(stage_role)


def _progress(run: Run) -> float:
    passed = sum(1 for s in run.stages if s.status == StageStatus.PASSED)
    return round(passed / _TOTAL_STAGES, 2)


def _order_key(agent: LiveAgent) -> int:
    return ROLE_ORDER.index(agent.role) if agent.role in ROLE_ORDER else len(ROLE_ORDER)


def build_live_agents(
    definitions: list[AgentDefinition], active_runs: list[Run]
) -> list[LiveAgent]:
    """Join the enabled roster with active runs into one row per role.

    Each enabled AgentDefinition becomes an idle row; an active run whose current
    stage maps to a roster role marks that row running. Concurrent same-role runs
    collapse to the most-recently-started one.
    """
    rows: dict[AgentRole, LiveAgent] = {}
    for d in definitions:
        if not d.enabled:
            continue
        rows.setdefault(d.role, LiveAgent(role=d.role, model=d.model_alias))

    # Sort oldest-first so the most recent run overwrites last (wins).
    def _started(r: Run):
        return r.started_at or r.created_at or datetime.min

    for run in sorted(active_runs, key=_started):
        role = _current_agent_role(run)
        if role is None or role not in rows:
            continue
        rows[role] = LiveAgent(
            role=role,
            model=rows[role].model,
            status="running",
            run_id=run.id,
            work_item_id=run.work_item_id,
            current_stage=run.current_stage,
            progress=_progress(run),
            token_usage=run.token_usage,
        )

    return sorted(rows.values(), key=_order_key)
