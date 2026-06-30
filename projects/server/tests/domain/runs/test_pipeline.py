from dataclasses import dataclass

from domain.runs.pipeline import Advance, Finish, GateStep, Retry, next_step
from domain.runs.run import GateKind, Run, RunStatus, Stage


@dataclass
class R:  # minimal stand-in for StageResult (next_step reads .passed only)
    passed: bool


def _run(stage, autonomy="gated_all", **kw):
    return Run(owner_id="u", work_item_id="w", project_id="p",
               autonomy_level=autonomy, current_stage=stage, **kw)


def test_plan_passed_requests_plan_gate_when_gated_all():
    assert next_step(_run(Stage.PLAN), R(True)) == GateStep(GateKind.PLAN)


def test_plan_gate_skipped_when_gated_merge():
    assert next_step(_run(Stage.PLAN, "gated_merge"), R(True)) == Advance(Stage.PROVISION)


def test_resolved_plan_gate_advances():
    r = _run(Stage.PLAN, resolved_gates=[GateKind.PLAN])
    assert next_step(r, R(True)) == Advance(Stage.PROVISION)


def test_provision_and_implement_advance():
    assert next_step(_run(Stage.PROVISION), R(True)) == Advance(Stage.IMPLEMENT)
    assert next_step(_run(Stage.IMPLEMENT), R(True)) == Advance(Stage.VERIFY)


def test_verify_passed_requests_merge_gate():
    assert next_step(_run(Stage.VERIFY), R(True)) == GateStep(GateKind.MERGE)


def test_verify_passed_full_auto_advances_to_pr():
    assert next_step(_run(Stage.VERIFY, "full_auto"), R(True)) == Advance(Stage.PR)


def test_verify_failed_retries_implement_until_limit():
    assert next_step(_run(Stage.VERIFY, verify_attempts=0), R(False)) == Retry(Stage.IMPLEMENT)
    result = next_step(_run(Stage.VERIFY, verify_attempts=3, max_verify_loops=3), R(False))
    assert result == Finish(RunStatus.FAILED)


def test_merge_gate_resolved_then_pr_learn_finish():
    r = _run(Stage.VERIFY, resolved_gates=[GateKind.MERGE])
    assert next_step(r, R(True)) == Advance(Stage.PR)
    assert next_step(_run(Stage.PR), R(True)) == Advance(Stage.LEARN)
    assert next_step(_run(Stage.LEARN), R(True)) == Finish(RunStatus.SUCCEEDED)
