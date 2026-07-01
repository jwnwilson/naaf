from enum import StrEnum

from domain.base import Entity


class NotificationType(StrEnum):
    GATE_PENDING = "gate_pending"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


class Notification(Entity):
    owner_id: str
    run_id: str
    work_item_id: str | None = None
    type: NotificationType
    title: str
    body: str = ""
    read: bool = False
    source_seq: int
