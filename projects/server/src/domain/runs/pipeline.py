from dataclasses import dataclass

from domain.runs.gates import requires_merge_gate, requires_plan_gate
from domain.runs.run import GateKind, Run, RunStatus, Stage

_ORDER = [Stage.PLAN, Stage.PROVISION, Stage.IMPLEMENT, Stage.VERIFY, Stage.PR, Stage.LEARN]


@dataclass(frozen=True)
class Advance:
    stage: Stage


@dataclass(frozen=True)
class GateStep:
    kind: GateKind


@dataclass(frozen=True)
class Retry:
    stage: Stage


@dataclass(frozen=True)
class Finish:
    status: RunStatus


Step = Advance | GateStep | Retry | Finish


def _next_stage(stage: Stage) -> Stage | None:
    i = _ORDER.index(stage)
    return _ORDER[i + 1] if i + 1 < len(_ORDER) else None


def _gate_after(stage: Stage, autonomy: str) -> GateKind | None:
    if stage is Stage.PLAN and requires_plan_gate(autonomy):
        return GateKind.PLAN
    if stage is Stage.VERIFY and requires_merge_gate(autonomy):
        return GateKind.MERGE
    return None


def next_step(run: Run, result) -> Step:
    """Pure transition: given the just-completed stage's result, what's next?

    `result` only needs a `.passed: bool` attribute.
    """
    current = run.current_stage
    if current is None:
        return Finish(RunStatus.SUCCEEDED)

    if current is Stage.VERIFY and not result.passed:
        if run.verify_attempts < run.max_verify_loops:
            return Retry(Stage.IMPLEMENT)
        return Finish(RunStatus.FAILED)

    gate = _gate_after(current, run.autonomy_level)
    if gate is not None and gate not in run.resolved_gates and run.pending_gate is None:
        return GateStep(gate)

    nxt = _next_stage(current)
    if nxt is None:
        return Finish(RunStatus.SUCCEEDED)
    return Advance(nxt)
