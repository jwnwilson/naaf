"""subscription_runner — builds the per-subscription UoW + context factories
and calls process_subscription.

Pure function: no Celery dependency, no module-level DB/broker imports.
All heavy imports happen inside the function body.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.agent.runtime import AgentRuntime
    from sqlalchemy.orm import sessionmaker


def run_subscription(
    name: str,
    session_factory: sessionmaker,
    runtime: AgentRuntime | None,
    chat_responder: object | None = None,
    lead_orchestrator: object | None = None,
    max_items: int = 1000,
) -> int:
    """Find subscription *name* in the registry, wire its factories, and drain it.

    Args:
        name:            subscription name — must match a ``Subscription.name``
                         in ``SUBSCRIPTIONS``.
        session_factory: SQLAlchemy ``sessionmaker`` (built by ``_deps()`` in
                         celery_app).
        runtime:         ``AgentRuntime`` instance (``FakeAgentRuntime`` or real).
        max_items:       Safety cap forwarded to ``process_subscription``.

    Returns:
        Number of items processed (0 if source was already empty).

    Raises:
        KeyError: if *name* is not found in ``SUBSCRIPTIONS``.
    """
    from adapters.agent.factory import build_agent_deps
    from adapters.agent.secrets_resolver import SecretResolver
    from adapters.bus.factory import build_message_bus
    from adapters.database.repositories import (
        MessageRepository,
        NotificationRepository,
        ProjectRepository,
        RunEventRepository,
        RunRepository,
        SecretRepository,
        WorkItemRepository,
    )
    from adapters.database.uow import SqlUnitOfWork
    from adapters.security.cipher import SecretCipher

    from interactors.worker.handlers import HandlerContext
    from interactors.worker.pubsub import process_subscription
    from interactors.worker.registry import SUBSCRIPTIONS

    # --- look up registration ---
    try:
        subscription = next(s for s in SUBSCRIPTIONS if s.name == name)
    except StopIteration:
        raise KeyError(f"No subscription registered with name {name!r}") from None

    # Instantiate the source once per tick (lambda / class call)
    source = subscription.source_factory()

    # Thin binding: process_subscription expects .source + .subscribers
    class _BoundSub:
        pass

    bound = _BoundSub()
    bound.source = source  # type: ignore[attr-defined]
    bound.subscribers = subscription.subscribers  # type: ignore[attr-defined]

    # --- unscoped UoW (system-level; ctx_factory adds owner-scope per item) ---
    def uow_factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory)

    # --- per-item owner-scoped context ---
    from adapters.storage.factory import build_storage

    from interactors.api.settings import Settings as _Settings
    _s = _Settings()
    _storage = build_storage(_s)
    _cipher = SecretCipher(_s.secret_key)

    def ctx_factory(uow: SqlUnitOfWork, item: object) -> HandlerContext:
        owner_id: str = item.owner_id  # type: ignore[attr-defined]
        scope = {"owner_id": owner_id}

        # Per-owner agent deps: build owner-specific deps when the owner has stored
        # secrets, or always in claude_cli mode (the MCP server is owner-scoped and
        # no global owner exists). Otherwise reuse the process-global (env) deps.
        secrets = SecretRepository(uow.session, required_filters=scope)
        resolver = SecretResolver(secrets, _cipher, _s)
        if _s.llm_provider == "claude_cli" or resolver.has_any_stored():
            _rt, _chat, _orch = build_agent_deps(
                _s,
                anthropic_api_key=resolver.anthropic_api_key(),
                github_token=resolver.github_token(),
                claude_oauth_token=resolver.claude_oauth_token(),
                owner_id=owner_id,
            )
        else:
            _rt, _chat, _orch = runtime, chat_responder, lead_orchestrator

        return HandlerContext(
            runs=RunRepository(uow.session, required_filters=scope),
            run_events=RunEventRepository(uow.session, required_filters=scope),
            work_items=WorkItemRepository(uow.session, required_filters=scope),
            notifications=NotificationRepository(uow.session, required_filters=scope),
            messages=MessageRepository(uow.session, required_filters=scope),
            bus=build_message_bus(uow),
            runtime=_rt,
            projects=ProjectRepository(uow.session, required_filters=scope),
            workspace_root=_s.workspace_root,
            role_aliases=_s.role_model_aliases,
            model_prices=_s.model_prices,
            storage=_storage,
            chat_responder=_chat,
            lead_orchestrator=_orch,
            session_factory=session_factory,
        )

    return process_subscription(bound, uow_factory, ctx_factory, max_items=max_items)
