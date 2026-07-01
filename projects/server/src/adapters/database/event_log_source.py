import logging

from domain.messaging.source import Item, PoisonOutcome
from interactors.dispatcher.subscriber import CursorState  # moves to domain/messaging in Task 3

from adapters.database.repositories import RunEventRepository, SubscriberCursorRepository

logger = logging.getLogger(__name__)


class EventLogSource:
    def __init__(self, subscriber_name: str, max_retries: int = 3):
        self.subscriber_name = subscriber_name
        self.max_retries = max_retries

    def fetch_next(self, uow) -> Item | None:
        store = SubscriberCursorRepository(uow.session)
        state = store.get(self.subscriber_name)
        events = RunEventRepository(uow.session).list_after(state.last_global_seq, limit=1)
        if not events:
            return None
        e = events[0]
        return Item(message=e, owner_id=e.owner_id, position=e.global_seq)

    def advance(self, item: Item, uow) -> None:
        SubscriberCursorRepository(uow.session).save(
            self.subscriber_name, CursorState(last_global_seq=item.position, retries=0)
        )

    def on_poison(self, item: Item, exc: Exception, uow_factory) -> PoisonOutcome:
        uow = uow_factory()
        with uow.transaction():
            store = SubscriberCursorRepository(uow.session)
            state = store.get(self.subscriber_name)
            retries = state.retries + 1
            if retries < self.max_retries:
                store.save(self.subscriber_name, CursorState(
                    last_global_seq=state.last_global_seq, retries=retries))
                return PoisonOutcome.STOP
            logger.error(
                "subscriber %s dead-lettering global_seq=%s after %s retries",
                self.subscriber_name, item.position, retries,
                exc_info=exc,
            )
            store.save(self.subscriber_name, CursorState(last_global_seq=item.position, retries=0))
            return PoisonOutcome.CONTINUE
