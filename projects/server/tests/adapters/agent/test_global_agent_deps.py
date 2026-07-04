from adapters.agent.factory import build_global_agent_deps
from interactors.api.settings import Settings


def test_global_deps_are_none_without_llm_creds():
    # claude_code runtime + claude provider + no env key: globals can't build.
    # They must be None so per-owner secrets (Settings > Secrets) provide creds
    # instead of the worker crashing on startup.
    s = Settings(agent_runtime="claude_code", llm_provider="claude", anthropic_api_key="")
    assert build_global_agent_deps(s) == (None, None, None)


def test_global_deps_build_for_fake_runtime():
    rt, chat, orch = build_global_agent_deps(Settings(agent_runtime="fake"))
    assert rt is not None and chat is not None and orch is not None


def test_global_deps_build_with_env_key():
    s = Settings(agent_runtime="claude_code", llm_provider="claude", anthropic_api_key="sk-test")
    rt, chat, orch = build_global_agent_deps(s)
    assert rt is not None and chat is not None and orch is not None
