from datetime import UTC, datetime

from domain.live_agents import build_live_agents
from domain.runs.run import Run, RunStatus, Stage, StageState, StageStatus
from domain.team import AgentDefinition, AgentRole


def _defn(role: AgentRole, model: str = "sonnet") -> AgentDefinition:
    return AgentDefinition(owner_id="o", team_id="t", role=role, model_alias=model)


def _run(stage: Stage, role: str, *, status=RunStatus.RUNNING, wi="wi1",
         passed: int = 0, tokens: int = 0, started=None) -> Run:
    stages = [StageState(stage=stage, status=StageStatus.RUNNING, role=role)]
    stages += [StageState(stage=Stage.PLAN, status=StageStatus.PASSED)] * passed
    return Run(
        owner_id="o", work_item_id=wi, project_id="p", autonomy_level="gated_all",
        status=status, current_stage=stage, stages=stages, token_usage=tokens,
        started_at=started,
    )


def test_all_roster_roles_idle_when_no_active_runs():
    rows = build_live_agents([_defn(AgentRole.LEAD), _defn(AgentRole.QA)], [])
    assert {r.role for r in rows} == {AgentRole.LEAD, AgentRole.QA}
    assert all(r.status == "idle" and r.run_id is None and r.token_usage == 0 for r in rows)


def test_engineer_stage_lights_up_backend_role():
    rows = build_live_agents(
        [_defn(AgentRole.BACKEND)],
        [_run(Stage.IMPLEMENT, "engineer", wi="wiX", tokens=500)],
    )
    backend = next(r for r in rows if r.role == AgentRole.BACKEND)
    assert backend.status == "running"
    assert backend.work_item_id == "wiX"
    assert backend.current_stage == Stage.IMPLEMENT
    assert backend.token_usage == 500


def test_lead_and_qa_mappings():
    rows = build_live_agents(
        [_defn(AgentRole.LEAD), _defn(AgentRole.QA)],
        [_run(Stage.PLAN, "lead"), _run(Stage.VERIFY, "qa")],
    )
    by_role = {r.role: r for r in rows}
    assert by_role[AgentRole.LEAD].status == "running"
    assert by_role[AgentRole.QA].status == "running"


def test_awaiting_gate_counts_as_running():
    rows = build_live_agents(
        [_defn(AgentRole.LEAD)],
        [_run(Stage.PLAN, "lead", status=RunStatus.AWAITING_GATE)],
    )
    assert rows[0].status == "running"


def test_progress_is_passed_over_total():
    rows = build_live_agents(
        [_defn(AgentRole.BACKEND)],
        [_run(Stage.IMPLEMENT, "engineer", passed=3)],
    )
    assert rows[0].progress == 0.5  # 3 passed / 6 total stages


def test_two_runs_same_role_most_recent_wins():
    older = _run(Stage.IMPLEMENT, "engineer", wi="old",
                 started=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _run(Stage.IMPLEMENT, "engineer", wi="new",
                 started=datetime(2026, 6, 1, tzinfo=UTC))
    rows = build_live_agents([_defn(AgentRole.BACKEND)], [older, newer])
    backend = next(r for r in rows if r.role == AgentRole.BACKEND)
    assert backend.work_item_id == "new"


def test_run_role_without_roster_row_lights_nothing():
    rows = build_live_agents([_defn(AgentRole.LEAD)], [_run(Stage.IMPLEMENT, "engineer")])
    assert rows[0].role == AgentRole.LEAD and rows[0].status == "idle"


def test_disabled_definition_produces_no_row():
    disabled = _defn(AgentRole.LEAD)
    disabled = disabled.model_copy(update={"enabled": False})
    rows = build_live_agents([disabled, _defn(AgentRole.QA)], [])
    assert [r.role for r in rows] == [AgentRole.QA]


def test_rows_in_fixed_role_order():
    rows = build_live_agents(
        [_defn(AgentRole.QA), _defn(AgentRole.LEAD), _defn(AgentRole.BACKEND)], []
    )
    assert [r.role for r in rows] == [AgentRole.LEAD, AgentRole.BACKEND, AgentRole.QA]
