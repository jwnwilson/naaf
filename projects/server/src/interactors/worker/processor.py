import logging

from adapters.bus.sql import SqlMessageBus
from adapters.database.repositories import RunEventRepository, RunRepository, WorkItemRepository

from interactors.worker.handlers import HandlerContext, couple, dispatch


def _dead_letter(msg, exc, session_factory) -> None:
    """Isolate a poison message: mark it consumed and fail its run in a fresh transaction.

    This prevents the message from being redelivered (claim_next skips status=done rows)
    and ensures the run doesn't hang indefinitely in an intermediate state.
    """
    from domain.base import utcnow
    from domain.runs.events import EventType, RunEvent
    from domain.runs.run import RunStatus

    session = session_factory()
    try:
        bus = SqlMessageBus(session)
        # (i) dead-letter the message — status=done prevents claim_next from returning it again
        bus.ack(msg)

        # (ii) fail the run so it doesn't hang
        scope = {"owner_id": msg.owner_id}
        runs = RunRepository(session, required_filters=scope)
        run_events = RunEventRepository(session, required_filters=scope)
        work_items = WorkItemRepository(session, required_filters=scope)
        try:
            run = runs.read(msg.run_id)
            run = runs.update(run.id, run.model_copy(update={
                "status": RunStatus.FAILED,
                "ended_at": utcnow(),
            }))
            run_events.create(RunEvent(
                owner_id="",
                run_id=run.id,
                type=EventType.RUN_FINISHED,
                payload={"status": "failed", "error": str(exc)},
            ))
            # best-effort work-item coupling — skip on transition error
            ctx = HandlerContext(
                runs=runs,
                run_events=run_events,
                work_items=work_items,
                bus=bus,
                runtime=None,
            )
            try:
                couple(ctx, run)
            except Exception:
                pass
        except Exception as inner:
            logging.warning("dead_letter: could not fail run for message %s: %s", msg.id, inner)

        session.commit()
    except Exception:
        session.rollback()
        logging.exception("dead_letter: cleanup itself failed for message %s", msg.id)
    finally:
        session.close()


def process_next(session_factory, runtime) -> bool:
    """Claim one bus message, dispatch it, ack, commit. Returns True if processed."""
    session = session_factory()
    try:
        bus = SqlMessageBus(session)
        msg = bus.claim_next()
        if msg is None:
            session.commit()
            return False
        scope = {"owner_id": msg.owner_id}
        ctx = HandlerContext(
            runs=RunRepository(session, required_filters=scope),
            run_events=RunEventRepository(session, required_filters=scope),
            work_items=WorkItemRepository(session, required_filters=scope),
            bus=bus,
            runtime=runtime,
        )
        try:
            dispatch(msg, ctx)
        except Exception as exc:
            session.rollback()
            logging.exception("worker: dispatch failed for message %s", msg.id)
            _dead_letter(msg, exc, session_factory)
            return True
        bus.ack(msg)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
