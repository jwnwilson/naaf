from domain.agent.runtime import AgentRuntime, LlmAgentRuntime

from adapters.agent.llm.claude import ClaudeLLMAdapter
from adapters.agent.workspace.local import LocalWorkspace


def build_llm_adapter(settings):
    if settings.llm_provider == "claude":
        if not settings.anthropic_api_key:
            raise ValueError("naaf_anthropic_api_key is required when naaf_llm_provider=claude")
        return ClaudeLLMAdapter(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            aliases=settings.model_aliases,
        )
    if settings.llm_provider == "litellm":
        if not settings.litellm_base_url or not settings.litellm_key:
            raise ValueError(
                "naaf_litellm_base_url and naaf_litellm_key are required "
                "when naaf_llm_provider=litellm"
            )
        from adapters.agent.llm.litellm import LiteLLMAdapter
        return LiteLLMAdapter(base_url=settings.litellm_base_url, key=settings.litellm_key)
    raise ValueError(f"unknown llm_provider: {settings.llm_provider}")


def build_runtime(settings) -> AgentRuntime:
    if settings.agent_runtime == "fake":
        from adapters.agent.runtime.fake import FakeAgentRuntime
        return FakeAgentRuntime()
    return LlmAgentRuntime(
        build_llm_adapter(settings),
        LocalWorkspace,
        settings.agent_max_iterations,
    )


def build_chat_responder(settings):
    """Return the appropriate ChatResponder for the configured runtime.

    Returns EchoChatResponder for ``agent_runtime=fake`` (offline/tests); otherwise
    returns LlmChatResponder wired to the configured LLM adapter.
    """
    from adapters.agent.chat.echo import EchoChatResponder
    if settings.agent_runtime == "fake":
        return EchoChatResponder()
    from adapters.agent.chat.llm import LlmChatResponder
    return LlmChatResponder(build_llm_adapter(settings))


def build_orchestrator(settings):
    """Return the LeadOrchestrator for the project-thread lead.

    EchoOrchestrator for ``agent_runtime=fake`` (offline/tests); otherwise the
    LLM-backed LlmOrchestrator wired to the configured LLM adapter.
    """
    from adapters.agent.chat.orchestrator_echo import EchoOrchestrator
    if settings.agent_runtime == "fake":
        return EchoOrchestrator()
    from adapters.agent.chat.orchestrator_llm import LlmOrchestrator
    return LlmOrchestrator(build_llm_adapter(settings))


def build_agent_deps(settings, *, anthropic_api_key: str, github_token: str):
    """Build (runtime, chat_responder, orchestrator) for a specific owner's secrets.

    The Anthropic key overrides the settings value; the GitHub token is injected
    into the run runtime's workspace env so the agent's git/gh commands use it.
    Falls through to the offline impls when ``agent_runtime=fake``.
    """
    if settings.agent_runtime == "fake":
        return build_runtime(settings), build_chat_responder(settings), build_orchestrator(settings)

    from adapters.agent.chat.llm import LlmChatResponder
    from adapters.agent.chat.orchestrator_llm import LlmOrchestrator

    owner_settings = settings.model_copy(update={"anthropic_api_key": anthropic_api_key})
    adapter = build_llm_adapter(owner_settings)
    env = {"GH_TOKEN": github_token} if github_token else None

    def workspace_factory(path: str) -> LocalWorkspace:
        return LocalWorkspace(path, env=env)

    runtime = LlmAgentRuntime(adapter, workspace_factory, settings.agent_max_iterations)
    return runtime, LlmChatResponder(adapter), LlmOrchestrator(adapter)
