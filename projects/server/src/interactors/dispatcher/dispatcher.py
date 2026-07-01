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
                try:
                    event = RunEvent.model_validate(row)
                    if sub.interested_in(event):
                        sub.handle(event, session)
                    # Success path: advance cursor and commit this event atomically.
                    store.save(sub.name, CursorState(last_global_seq=event.global_seq, retries=0))
                    session.commit()
                    handled += 1
                    state = CursorState(last_global_seq=event.global_seq, retries=0)
                except Exception:
                    # Rollback discards THIS event's partial writes; earlier events are safe
                    # because they were already individually committed.
                    session.rollback()
                    retries = state.retries + 1
                    if retries < MAX_SUBSCRIBER_RETRIES:
                        # Keep cursor position; increment retry counter; retry next tick.
                        store.save(
                            sub.name,
                            CursorState(last_global_seq=state.last_global_seq, retries=retries),
                        )
                        session.commit()
                        return handled
                    # Retry cap reached: dead-letter — log and advance past the poison event.
                    logger.exception(
                        "subscriber %s dead-lettering event global_seq=%s after %s retries",
                        sub.name,
                        row.global_seq,
                        retries,
                    )
                    store.save(
                        sub.name,
                        CursorState(last_global_seq=row.global_seq, retries=0),
                    )
                    session.commit()
                    handled += 1
                    state = CursorState(last_global_seq=row.global_seq, retries=0)
                    # Continue to next event in the batch.
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
