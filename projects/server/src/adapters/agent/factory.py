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
    if settings.llm_provider == "scripted":
        from adapters.agent.scripted.adapter import ScriptedLLMAdapter
        return ScriptedLLMAdapter()
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


def build_claude_cli_deps(
    settings, *, owner_id: str, github_token: str, claude_oauth_token: str = ""
):
    """Build (runtime, chat_responder, orchestrator) for the Claude subscription
    (via `claude -p`) — no Anthropic key. One ClaudeCliLLMAdapter powers all three
    (reusing LlmAgentRuntime/LlmChatResponder/LlmOrchestrator). The runtime's
    workspace_factory points the adapter at each stage's workspace; the adapter's
    MCP config is scoped to this owner so Claude Code can call naaf's tools."""
    from adapters.agent.chat.llm import LlmChatResponder
    from adapters.agent.chat.orchestrator_llm import LlmOrchestrator
    from adapters.agent.claude_cli.adapter import ClaudeCliLLMAdapter
    from adapters.agent.claude_cli.mcp_config import write_mcp_config

    mcp_path = write_mcp_config(owner_id=owner_id, db_url=settings.db_url) if owner_id else None
    adapter = ClaudeCliLLMAdapter(
        claude_bin=settings.claude_bin,
        mcp_config_path=mcp_path,
        github_token=github_token,
        claude_oauth_token=claude_oauth_token,
        timeout_s=settings.claude_timeout_s,
    )

    def workspace_factory(path: str) -> LocalWorkspace:
        adapter.set_cwd(path)  # run claude -p in this stage's workspace
        return LocalWorkspace(path)

    runtime = LlmAgentRuntime(adapter, workspace_factory, settings.agent_max_iterations)
    return runtime, LlmChatResponder(adapter), LlmOrchestrator(adapter)


def build_agent_deps(settings, *, anthropic_api_key: str = "", github_token: str = "",
                     owner_id: str = "", claude_oauth_token: str = ""):
    """Build (runtime, chat_responder, orchestrator) for a specific owner's secrets.

    The Anthropic key overrides the settings value; the GitHub token is injected
    into the run runtime's workspace env so the agent's git/gh commands use it.
    Falls through to the offline impls when ``agent_runtime=fake`` and to the
    Claude subscription when ``llm_provider=claude_cli``.
    """
    if settings.agent_runtime == "fake":
        return build_runtime(settings), build_chat_responder(settings), build_orchestrator(settings)

    if settings.llm_provider == "claude_cli":
        return build_claude_cli_deps(
            settings, owner_id=owner_id, github_token=github_token,
            claude_oauth_token=claude_oauth_token,
        )

    from adapters.agent.chat.llm import LlmChatResponder
    from adapters.agent.chat.orchestrator_llm import LlmOrchestrator

    owner_settings = settings.model_copy(update={"anthropic_api_key": anthropic_api_key})
    adapter = build_llm_adapter(owner_settings)
    env = {"GH_TOKEN": github_token} if github_token else None

    def workspace_factory(path: str) -> LocalWorkspace:
        return LocalWorkspace(path, env=env)

    runtime = LlmAgentRuntime(adapter, workspace_factory, settings.agent_max_iterations)
    return runtime, LlmChatResponder(adapter), LlmOrchestrator(adapter)


def build_global_agent_deps(settings) -> tuple[AgentRuntime | None, object, object]:
    """Process-global (env-based) agent deps for the worker's fallback path.

    Returns ``(None, None, None)`` when no LLM credentials are configured in the
    environment (e.g. keys live only in Settings > Secrets). Per-owner injection
    in ``ctx_factory`` then supplies credentials at run time; the worker must not
    crash at startup just because the global env key is absent.
    """
    try:
        return build_runtime(settings), build_chat_responder(settings), build_orchestrator(settings)
    except ValueError:
        return None, None, None
