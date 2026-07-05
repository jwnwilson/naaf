from domain.agent.runtime import AgentEvent, StageOutcome, StageResult
from domain.pricing import ModelPrice
from domain.runs.run import Run, RunStatus, Stage, StageState, StageStatus
from interactors.worker.handlers import HandlerContext, _finish_stage


class _Repo:
    def __init__(self):
        self.saved = None

    def read(self, _id):
        return self.saved

    def update(self, _id, dto):
        self.saved = dto
        return dto

    def create(self, dto):
        self.saved = dto
        return dto


def _ctx():
    return HandlerContext(
        runs=_Repo(), run_events=_Repo(), work_items=_Repo(), notifications=None,
        bus=None, runtime=None, messages=_Repo(),
        model_prices={"sonnet": ModelPrice(input=0.003, output=0.015)},
    )


def _run():
    return Run(
        owner_id="o", work_item_id="wi", project_id="p", autonomy_level="gated_all",
        status=RunStatus.RUNNING, current_stage=Stage.IMPLEMENT,
        stages=[StageState(stage=Stage.IMPLEMENT, status=StageStatus.RUNNING, role="engineer")],
    )


def test_finish_stage_accumulates_priced_cost_and_tokens():
    ctx = _ctx()
    ctx.runs.saved = _run()
    outcome = StageOutcome(
        events=[AgentEvent(message="hi")],
        result=StageResult(passed=True, summary="ok", tokens=3000,
                            input_tokens=1000, output_tokens=2000, model="sonnet"),
    )
    _finish_stage(ctx, ctx.runs.saved, "engineer", Stage.IMPLEMENT, outcome)
    saved = ctx.runs.saved
    assert saved.token_usage == 3000
    # 1000/1000*0.003 + 2000/1000*0.015 = 0.033
    assert round(saved.cost, 4) == 0.033


def test_finish_stage_unknown_model_costs_zero():
    ctx = _ctx()
    ctx.runs.saved = _run()
    outcome = StageOutcome(
        events=[], result=StageResult(passed=True, tokens=500, input_tokens=500, model="mystery"),
    )
    _finish_stage(ctx, ctx.runs.saved, "engineer", Stage.IMPLEMENT, outcome)
    assert ctx.runs.saved.cost == 0.0
