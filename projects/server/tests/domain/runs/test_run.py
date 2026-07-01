from domain.runs.run import GateKind, Run, RunStatus, Stage, StageState, StageStatus


def test_run_defaults():
    r = Run(owner_id="u1", work_item_id="w1", project_id="p1", autonomy_level="gated_all")
    assert r.status is RunStatus.QUEUED
    assert r.current_stage is None
    assert r.stages == []
    assert r.pending_gate is None
    assert r.resolved_gates == []
    assert r.verify_attempts == 0
    assert r.max_verify_loops == 3


def test_stage_state_and_enums():
    s = StageState(stage=Stage.PLAN, status=StageStatus.RUNNING, role="lead")
    assert s.stage is Stage.PLAN
    assert Stage.IMPLEMENT.value == "implement"
    assert GateKind.MERGE.value == "merge"


def test_run_is_immutable_via_model_copy():
    r = Run(owner_id="u1", work_item_id="w1", project_id="p1", autonomy_level="full_auto")
    r2 = r.model_copy(update={"status": RunStatus.RUNNING})
    assert r.status is RunStatus.QUEUED
    assert r2.status is RunStatus.RUNNING
