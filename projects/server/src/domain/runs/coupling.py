from domain.runs.run import GateKind, Run, RunStatus


def work_item_status_for(run: Run) -> str | None:
    if run.status is RunStatus.RUNNING:
        return "in_progress"
    if run.status is RunStatus.AWAITING_GATE and run.pending_gate is not None \
            and run.pending_gate.kind is GateKind.MERGE:
        return "in_review"
    if run.status is RunStatus.SUCCEEDED:
        return "done"
    if run.status in (RunStatus.FAILED, RunStatus.CANCELLED):
        return "in_progress"
    return None
