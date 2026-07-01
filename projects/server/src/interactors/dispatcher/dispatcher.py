import logging

from adapters.database.orm import RunEventRow
from adapters.dispatcher.cursor_store import SqlSubscriberCursorStore
from domain.runs.events import RunEvent
from sqlalchemy import select

from interactors.dispatcher.subscriber import CursorState, EventSubscriber

logger = logging.getLogger(__name__)

MAX_SUBSCRIBER_RETRIES = 3
BATCH = 100


def dispatch_events(session_factory, subscribers: list[EventSubscriber] | None = None) -> int:
    from interactors.dispatcher.registry import SUBSCRIBERS

    subs = SUBSCRIBERS if subscribers is None else subscribers
    return sum(_dispatch_one(session_factory, s) for s in subs)


def _dispatch_one(session_factory, sub: EventSubscriber) -> int:
    handled = 0
    while True:
        session = session_factory()
        try:
            store = SqlSubscriberCursorStore(session)
            state = store.get(sub.name)
            rows = (
                session.execute(
                    select(RunEventRow)
                    .where(
                        RunEventRow.global_seq.isnot(None),
                        RunEventRow.global_seq > state.last_global_seq,
                    )
                    .order_by(RunEventRow.global_seq)
                    .limit(BATCH)
                )
                .scalars()
                .all()
            )
            if not rows:
                session.commit()
                return handled
            for row in rows:
                event = RunEvent.model_validate(row)
                if sub.interested_in(event):
                    try:
                        sub.handle(event, session)
                    except Exception:  # isolate: never let one subscriber/event break others
                        state = CursorState(
                            last_global_seq=state.last_global_seq,
                            retries=state.retries + 1,
                        )
                        if state.retries < MAX_SUBSCRIBER_RETRIES:
                            store.save(sub.name, state)  # keep cursor; retry next tick
                            session.commit()
                            return handled
                        logger.exception(
                            "subscriber %s dead-lettering event global_seq=%s after %s retries",
                            sub.name,
                            event.global_seq,
                            state.retries,
                        )
                        # fall through: advance past the poison event
                state = CursorState(last_global_seq=event.global_seq, retries=0)
                store.save(sub.name, state)
                handled += 1
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
