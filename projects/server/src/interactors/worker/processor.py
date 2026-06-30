from adapters.database.repositories import RunEventRepository, RunRepository, WorkItemRepository

from interactors.worker.handlers import HandlerContext, dispatch


def process_next(session_factory, bus, runtime) -> bool:
    """Claim one bus message, dispatch it, ack, commit. Returns True if processed."""
    session = session_factory()
    try:
        msg = bus.claim_next(session)
        if msg is None:
            session.commit()
            return False
        scope = {"owner_id": msg.owner_id}
        ctx = HandlerContext(
            runs=RunRepository(session, required_filters=scope),
            run_events=RunEventRepository(session, required_filters=scope),
            work_items=WorkItemRepository(session, required_filters=scope),
            bus=bus,
            session=session,
            runtime=runtime,
        )
        dispatch(msg, ctx)
        bus.ack(msg, session)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
