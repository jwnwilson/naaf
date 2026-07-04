from adapters.agent.factory import build_agent_deps
from interactors.api.settings import Settings


def test_fake_runtime_returns_offline_impls():
    runtime, chat, orch = build_agent_deps(
        Settings(agent_runtime="fake"), anthropic_api_key="", github_token="",
    )
    assert runtime.__class__.__name__ == "FakeAgentRuntime"
    assert chat.__class__.__name__ == "EchoChatResponder"
    assert orch.__class__.__name__ == "EchoOrchestrator"


def test_real_runtime_injects_github_token_into_its_workspace(tmp_path):
    # ClaudeLLMAdapter is constructed (no network call) with a dummy key.
    settings = Settings(agent_runtime="claude_code", llm_provider="claude")
    runtime, _chat, _orch = build_agent_deps(
        settings, anthropic_api_key="sk-test", github_token="ghp_tok",
    )
    ws = runtime._workspace_factory(str(tmp_path))
    r = ws.bash("echo $GH_TOKEN", timeout_s=10)
    assert r.stdout.strip() == "ghp_tok"
