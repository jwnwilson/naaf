from domain.agent.context import StageContext
from domain.agent.runtime import AgentEvent, StageOutcome, StageResult
from domain.runs.run import Stage

TOKENS_PER_STEP = 350  # deterministic placeholder; real token counts arrive with the A5 runtime

_SCRIPT = {
    Stage.PLAN: [
        "Reading ticket + project memory",
        "Drafting implementation plan",
        "Plan ready (plan.md)",
    ],
    Stage.PROVISION: ["Provisioning workspace (stub)"],
    Stage.IMPLEMENT: ["Checked out agent branch", "Editing files", "Committed changes"],
    Stage.VERIFY: ["Running tests", "Checking acceptance criteria"],
    Stage.PR: ["Would open PR (stub)"],
    Stage.LEARN: ["Distilling run into memory (stub)"],
}


class FakeAgentRuntime:
    """Scripted, no-LLM runtime. Passes every stage, except VERIFY can be made
    to fail the first `fail_verify_times` attempts to exercise the retry path."""

    def __init__(self, fail_verify_times: int = 0):
        self.fail_verify_times = fail_verify_times

    def run_stage(self, role: str, stage: Stage, ctx: StageContext) -> StageOutcome:
        events = [AgentEvent(message=m) for m in _SCRIPT.get(stage, [f"{stage.value} step"])]
        passed = True
        if stage is Stage.VERIFY and ctx.verify_attempts < self.fail_verify_times:
            passed = False
        summary = "ok" if passed else "verification failed"
        tokens = TOKENS_PER_STEP * len(events)
        result = StageResult(passed=passed, summary=summary, tokens=tokens)
        return StageOutcome(events=events, result=result)
