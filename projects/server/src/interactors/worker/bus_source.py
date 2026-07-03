import logging
from collections.abc import Callable

from adapters.bus.factory import build_message_bus
from adapters.database.repositories import RunEventRepository, RunRepository, WorkItemRepository
from adapters.database.uow import SqlUnitOfWork
from domain.base import utcnow
from domain.messaging.source import Item, PoisonOutcome
from domain.runs.events import EventType, RunEvent
from domain.runs.run import RunStatus

from interactors.worker.handlers import HandlerContext, couple

logger = logging.getLogger(__name__)


class BusSource:
    """MessageSource that drains the agent-message work queue.

    fetch_next  — claims the next pending bus message as an Item.
    advance     — acks the message (marks it done so it is not redelivered).
    on_poison   — acks the message and fails its run in a fresh transaction,
                  returning PoisonOutcome.CONTINUE so the engine keeps running.
    """

    def __init__(self, roles: list[str] | None = None) -> None:
        self._roles = roles or None

    def fetch_next(self, uow) -> Item | None:
        msg = build_message_bus(uow.session).claim_next(self._roles)
        if msg is None:
            return None
        return Item(message=msg, owner_id=msg.owner_id, position=0)

    def advance(self, item: Item, uow) -> None:
        build_message_bus(uow.session).ack(item.message)

    def on_poison(
        self, item: Item, exc: Exception, uow_factory: Callable[[], SqlUnitOfWork]
    ) -> PoisonOutcome:
        """Isolate a poison message: ack it and fail its run in a fresh transaction.

        Converted from interactors.worker.processor._dead_letter to use uow.transaction()
        instead of manual session/commit.  Always returns CONTINUE so the engine loop
        keeps draining the bus after a poison message.
        """
        msg = item.message
        try:
            uow = uow_factory()
            with uow.transaction():
                bus = build_message_bus(uow.session)
                # (i) ack immediately — prevents re-delivery on the next claim_next
                bus.ack(msg)

                scope = {"owner_id": msg.owner_id}
                runs = RunRepository(uow.session, required_filters=scope)
                run_events = RunEventRepository(uow.session, required_filters=scope)
                work_items = WorkItemRepository(uow.session, required_filters=scope)

                # (ii) fail the run so it does not hang in an intermediate state
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
                    # (iii) best-effort work-item coupling — skip on transition error
                    ctx = HandlerContext(
                        runs=runs,
                        run_events=run_events,
                        work_items=work_items,
                        notifications=None,
                        bus=bus,
                        runtime=None,
                    )
                    try:
                        couple(ctx, run)
                    except Exception:
                        logger.warning(
                            "bus_source: couple failed for run %s", run.id, exc_info=True
                        )
                except Exception as inner:
                    logger.warning(
                        "bus_source: could not fail run for message %s: %s", msg.id, inner
                    )
        except Exception:
            logger.exception("bus_source: on_poison cleanup failed for message %s", msg.id)

        return PoisonOutcome.CONTINUE
