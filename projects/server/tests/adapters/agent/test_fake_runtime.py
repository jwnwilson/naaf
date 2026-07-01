from adapters.agent.runtime.fake import FakeAgentRuntime
from domain.runs.run import Stage


def test_fake_passes_by_default_and_emits_events():
    rt = FakeAgentRuntime()
    out = rt.run_stage("lead", Stage.PLAN, ctx={})
    assert out.result.passed is True
    assert len(out.events) >= 1
    assert all(e.message for e in out.events)


def test_fake_verify_fails_then_passes():
    rt = FakeAgentRuntime(fail_verify_times=1)
    first = rt.run_stage("qa", Stage.VERIFY, ctx={"verify_attempts": 0})
    second = rt.run_stage("qa", Stage.VERIFY, ctx={"verify_attempts": 1})
    assert first.result.passed is False
    assert second.result.passed is True
