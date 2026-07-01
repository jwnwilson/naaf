import pytest
from adapters.database.uow import SqlUnitOfWork
from domain.errors import IntegrityConflict
from domain.notifications.notification import Notification, NotificationType


def _uow(sf): return SqlUnitOfWork(sf, required_filters={"owner_id": "u1"})


def test_notification_round_trip(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        n = uow.notifications.create(Notification(owner_id="", run_id="r1",
            type=NotificationType.GATE_PENDING, title="Action needed", source_seq=7))
        got = uow.notifications.read(n.id)
    assert got.owner_id == "u1" and got.read is False and got.source_seq == 7


def test_source_seq_is_unique(session_factory):
    uow = _uow(session_factory)
    with pytest.raises(IntegrityConflict):
        with uow.transaction():
            uow.notifications.create(Notification(owner_id="", run_id="r1",
                type=NotificationType.RUN_SUCCEEDED, title="a", source_seq=9))
            uow.notifications.create(Notification(owner_id="", run_id="r2",
                type=NotificationType.RUN_SUCCEEDED, title="b", source_seq=9))
