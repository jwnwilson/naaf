from domain.notifications.notification import Notification, NotificationType
from domain.runs.events import EventType, RunEvent

_FINISH_STATUS_TYPE = {
    "succeeded": NotificationType.RUN_SUCCEEDED,
    "failed": NotificationType.RUN_FAILED,
    "cancelled": NotificationType.RUN_CANCELLED,
}


class NotificationSubscriber:
    name = "notifications"

    def interested_in(self, event: RunEvent) -> bool:
        return event.type in (EventType.GATE_REQUESTED, EventType.RUN_FINISHED)

    def handle(self, event: RunEvent, ctx: object) -> None:
        repo = ctx.notifications  # type: ignore[attr-defined]

        # Pre-check idempotency: skip if a notification already exists for this source_seq.
        existing = repo.read_multi(filters={"source_seq": event.global_seq}, page_size=1)
        if existing.results:
            return

        if event.type is EventType.GATE_REQUESTED:
            kind = event.payload.get("kind", "review")
            notif = Notification(
                owner_id="",
                run_id=event.run_id,
                type=NotificationType.GATE_PENDING,
                title="Action needed",
                body=f"Run {event.run_id} is awaiting {kind} approval",
                source_seq=event.global_seq,
            )
        else:  # RUN_FINISHED
            status = event.payload.get("status", "succeeded")
            notif = Notification(
                owner_id="",
                run_id=event.run_id,
                type=_FINISH_STATUS_TYPE.get(status, NotificationType.RUN_SUCCEEDED),
                title=f"Run {status}",
                body=f"Run {event.run_id} {status}",
                source_seq=event.global_seq,
            )

        repo.create(notif)
