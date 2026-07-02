import pytest
from adapters.agent.factory import build_llm_adapter, build_runtime
from adapters.agent.llm.claude import ClaudeLLMAdapter
from domain.agent.runtime import LlmAgentRuntime


class _S:  # minimal settings stand-in
    llm_provider = "claude"
    anthropic_api_key = "k"
    anthropic_base_url = ""
    model_aliases = {"opus": "claude-opus-4-8"}
    agent_max_iterations = 9
    agent_runtime = "claude_code"


def test_build_llm_adapter_returns_claude(monkeypatch):
    monkeypatch.setattr(ClaudeLLMAdapter, "__init__",
                        lambda self, **kw: setattr(self, "_client", object()) or None)
    assert isinstance(build_llm_adapter(_S()), ClaudeLLMAdapter)


def test_build_runtime_wires_local_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(ClaudeLLMAdapter, "__init__",
                        lambda self, **kw: setattr(self, "_client", object()) or None)
    rt = build_runtime(_S(), str(tmp_path))
    assert isinstance(rt, LlmAgentRuntime)


def test_build_llm_adapter_unknown_provider_raises():
    class S:
        llm_provider = "bogus"
    with pytest.raises(ValueError):
        build_llm_adapter(S())


def test_build_runtime_fake_returns_fake():
    from adapters.agent.runtime.fake import FakeAgentRuntime
    class S:
        agent_runtime = "fake"
    assert isinstance(build_runtime(S(), "/tmp/ws"), FakeAgentRuntime)
