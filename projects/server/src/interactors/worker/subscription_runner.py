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
    runtime: AgentRuntime,
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
    from adapters.bus.factory import build_message_bus
    from adapters.database.repositories import (
        NotificationRepository,
        ProjectRepository,
        RunEventRepository,
        RunRepository,
        WorkItemRepository,
    )
    from adapters.database.uow import SqlUnitOfWork

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
    from interactors.api.settings import Settings as _Settings
    _s = _Settings()

    def ctx_factory(uow: SqlUnitOfWork, item: object) -> HandlerContext:
        owner_id: str = item.owner_id  # type: ignore[attr-defined]
        scope = {"owner_id": owner_id}
        return HandlerContext(
            runs=RunRepository(uow.session, required_filters=scope),
            run_events=RunEventRepository(uow.session, required_filters=scope),
            work_items=WorkItemRepository(uow.session, required_filters=scope),
            notifications=NotificationRepository(uow.session, required_filters=scope),
            bus=build_message_bus(uow),
            runtime=runtime,
            projects=ProjectRepository(uow.session, required_filters=scope),
            workspace_root=_s.workspace_root,
            role_aliases=_s.role_model_aliases,
        )

    return process_subscription(bound, uow_factory, ctx_factory, max_items=max_items)
