from interactors.api.settings import Settings


def test_llm_defaults_to_claude():
    s = Settings()
    assert s.llm_provider == "claude"
    assert s.agent_max_iterations == 25


def test_naaf_env_prefix_overrides(monkeypatch):
    monkeypatch.setenv("naaf_llm_provider", "litellm")
    monkeypatch.setenv("naaf_agent_max_iterations", "5")
    s = Settings()
    assert s.llm_provider == "litellm"
    assert s.agent_max_iterations == 5


def test_role_and_model_aliases_have_defaults():
    s = Settings()
    assert s.model_aliases["opus"] == "claude-opus-4-8"
    assert s.role_model_aliases["engineer"] == "sonnet"
