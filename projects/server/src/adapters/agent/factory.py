from domain.agent.runtime import AgentRuntime, LlmAgentRuntime

from adapters.agent.llm.claude import ClaudeLLMAdapter
from adapters.agent.workspace.local import LocalWorkspace


def build_llm_adapter(settings):
    if settings.llm_provider == "claude":
        return ClaudeLLMAdapter(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            aliases=settings.model_aliases,
        )
    if settings.llm_provider == "litellm":
        from adapters.agent.llm.litellm import LiteLLMAdapter  # Phase 7
        return LiteLLMAdapter(base_url=settings.litellm_base_url, key=settings.litellm_key)
    raise ValueError(f"unknown llm_provider: {settings.llm_provider}")


def build_runtime(settings, workspace_root: str) -> AgentRuntime:
    if settings.agent_runtime == "fake":
        from adapters.agent.runtime.fake import FakeAgentRuntime
        return FakeAgentRuntime()
    return LlmAgentRuntime(
        build_llm_adapter(settings),
        LocalWorkspace(workspace_root),
        settings.agent_max_iterations,
    )
