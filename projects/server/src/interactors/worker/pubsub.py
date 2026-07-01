"""Unified pub/sub engine.

``process_subscription`` drains any subscription (agent-bus OR event-log fan-out)
via the ``MessageSource`` port, one item per ``uow.transaction()``, dispatching to
interested subscribers.  Poison isolation is delegated to ``source.on_poison``.
"""
from domain.messaging.source import PoisonOutcome


def process_subscription(subscription, uow_factory, ctx_factory) -> int:
    """Drain *subscription* until the source is empty; return total items handled.

    Args:
        subscription: any object with ``.source`` (MessageSource) and
                      ``.subscribers`` (list[Subscriber]).
        uow_factory:  callable ``() -> UnitOfWork`` — called once per item.
        ctx_factory:  callable ``(uow, item) -> HandlerContext`` — builds the
                      per-item owner-scoped context.

    Returns:
        Number of items handled (success + CONTINUE-recovered poison items).
    """
    handled = 0
    source = subscription.source
    while True:
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
