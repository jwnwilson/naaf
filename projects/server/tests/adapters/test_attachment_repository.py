import pytest
from adapters.database.uow import SqlUnitOfWork
from domain.attachments.attachment import Attachment


@pytest.fixture
def uow(session_factory):
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": "dev-user"})


def test_create_and_read_attachment_round_trips(uow):
    with uow.transaction() as u:
        created = u.attachments.create(
            Attachment(
                owner_id="",
                work_item_id="wi123",
                filename="mockup.png",
                content_type="image/png",
                size=42,
            )
        )
    with uow.transaction() as u:
        got = u.attachments.read(created.id)
    assert got.work_item_id == "wi123"
    assert got.filename == "mockup.png"
    assert got.content_type == "image/png"
    assert got.size == 42
    assert got.owner_id == "dev-user"  # stamped by required_filters


def test_list_by_work_item_filters(uow):
    with uow.transaction() as u:
        u.attachments.create(
            Attachment(
                owner_id="", work_item_id="wiA", filename="a.txt", content_type="text/plain", size=1
            )
        )
        u.attachments.create(
            Attachment(
                owner_id="", work_item_id="wiB", filename="b.txt", content_type="text/plain", size=1
            )
        )
    with uow.transaction() as u:
        page = u.attachments.read_multi(filters={"work_item_id": "wiA"})
    assert [a.filename for a in page.results] == ["a.txt"]
