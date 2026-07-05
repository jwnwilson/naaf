from adapters.agent.factory import build_llm_adapter
from adapters.agent.scripted.adapter import ScriptedLLMAdapter
from interactors.api.settings import Settings


def test_build_llm_adapter_returns_scripted_for_scripted_provider():
    settings = Settings().model_copy(update={"llm_provider": "scripted"})
    assert isinstance(build_llm_adapter(settings), ScriptedLLMAdapter)
