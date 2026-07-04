from adapters.agent.factory import build_agent_deps, build_global_agent_deps
from interactors.api.settings import Settings


def test_claude_cli_deps_build_without_any_api_key():
    s = Settings(agent_runtime="claude_code", llm_provider="claude_cli", anthropic_api_key="")
    runtime, chat, orch = build_agent_deps(s, github_token="ghp_x", owner_id="u1")
    assert runtime.__class__.__name__ == "LlmAgentRuntime"
    assert chat.__class__.__name__ == "LlmChatResponder"
    assert orch.__class__.__name__ == "LlmOrchestrator"
    # the adapter powering all three is the CLI adapter
    assert runtime._llm.__class__.__name__ == "ClaudeCliLLMAdapter"


def test_global_deps_none_in_claude_cli_mode():
    # No global owner → no MCP scoping; per-owner deps built in ctx_factory instead.
    s = Settings(agent_runtime="claude_code", llm_provider="claude_cli", anthropic_api_key="")
    assert build_global_agent_deps(s) == (None, None, None)
