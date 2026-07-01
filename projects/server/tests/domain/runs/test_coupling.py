from domain.runs.coupling import work_item_status_for
from domain.runs.run import Gate, GateKind, Run, RunStatus, Stage


def _run(status, **kw):
    return Run(
        owner_id="u",
        work_item_id="w",
        project_id="p",
        autonomy_level="gated_all",
        status=status,
        **kw,
    )


def test_running_to_in_progress():
    assert work_item_status_for(_run(RunStatus.RUNNING)) == "in_progress"


def test_merge_gate_to_in_review():
    r = _run(RunStatus.AWAITING_GATE, pending_gate=Gate(kind=GateKind.MERGE, stage=Stage.VERIFY))
    assert work_item_status_for(r) == "in_review"


def test_plan_gate_no_change():
    r = _run(RunStatus.AWAITING_GATE, pending_gate=Gate(kind=GateKind.PLAN, stage=Stage.PLAN))
    assert work_item_status_for(r) is None


def test_succeeded_done_failed_in_progress():
    assert work_item_status_for(_run(RunStatus.SUCCEEDED)) == "done"
    assert work_item_status_for(_run(RunStatus.FAILED)) == "in_progress"
    assert work_item_status_for(_run(RunStatus.CANCELLED)) == "in_progress"
