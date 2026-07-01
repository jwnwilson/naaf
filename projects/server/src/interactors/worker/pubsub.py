"""Unified pub/sub engine.

``process_subscription`` drains any subscription (agent-bus OR event-log fan-out)
via the ``MessageSource`` port, one item per ``uow.transaction()``, dispatching to
interested subscribers.  Poison isolation is delegated to ``source.on_poison``.
"""
from collections.abc import Callable
from typing import Any, Protocol

from domain.messaging.source import PoisonOutcome


class _Subscription(Protocol):
    """Structural type for any subscription object passed to process_subscription.

    Requires ``.source`` (MessageSource) and ``.subscribers`` (list[Subscriber]).
    """

    source: Any  # MessageSource
    subscribers: list  # list[Subscriber]


def process_subscription(
    subscription: Any,  # Any object satisfying _Subscription protocol
    uow_factory: Callable[[], Any],
    ctx_factory: Callable[..., Any],
    max_items: int = 1000,
) -> int:
    """Drain *subscription* until the source is empty or *max_items* is reached.

    Args:
        subscription: any object with ``.source`` (MessageSource) and
                      ``.subscribers`` (list[Subscriber]).
        uow_factory:  callable ``() -> UnitOfWork`` — called once per item.
        ctx_factory:  callable ``(uow, item) -> HandlerContext`` — builds the
                      per-item owner-scoped context.
        max_items:    safety cap — stop after this many handled items.  Guards
                      against a misbehaving source whose ``on_poison`` returns
                      CONTINUE without advancing the cursor (which would otherwise
                      spin forever, blocking the single worker thread).  The beat
                      task re-fires on the next tick, so a capped drain just
                      resumes then.

    Returns:
        Number of items handled (success + CONTINUE-recovered poison items).
    """
    handled = 0
    source = subscription.source
    while True:
        if handled >= max_items:
            return handled
        uow = uow_factory()
        item = None
        try:
            with uow.transaction():
                item = source.fetch_next(uow)
                if item is None:
                    return handled
                ctx = ctx_factory(uow, item)
                for sub in subscription.subscribers:
                    if sub.interested_in(item.message):
                        sub.handle(item.message, ctx)
                source.advance(item, uow)
            handled += 1
        except Exception as exc:
            if item is None:
                raise
            if source.on_poison(item, exc, uow_factory) is PoisonOutcome.STOP:
                return handled
            handled += 1
