from adapters.database.uow import SqlUnitOfWork
from domain.messaging.message import AuthorKind, Message


def _uow(sf, owner="u1"):
    return SqlUnitOfWork(sf, required_filters={"owner_id": owner})


def test_message_round_trip_stamps_owner(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        m = uow.messages.create(
            Message(owner_id="", thread_id="r1", author_kind=AuthorKind.USER, content="hello")
        )
        got = uow.messages.read(m.id)
    assert got.owner_id == "u1"
    assert got.content == "hello"
    assert got.author_kind == AuthorKind.USER


def test_messages_list_by_thread_oldest_first(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        for text in ("first", "second", "third"):
            uow.messages.create(
                Message(owner_id="", thread_id="r1", author_kind=AuthorKind.USER, content=text)
            )
        uow.messages.create(
            Message(owner_id="", thread_id="OTHER", author_kind=AuthorKind.USER, content="nope")
        )
        page = uow.messages.read_multi(filters={"thread_id": "r1"}, order_by="created_at")
    assert [m.content for m in page.results] == ["first", "second", "third"]
    assert page.total == 3


def test_messages_are_owner_scoped(session_factory):
    with _uow(session_factory, "u1").transaction() as uow:
        uow.messages.create(
            Message(owner_id="", thread_id="r1", author_kind=AuthorKind.USER, content="mine")
        )
    with _uow(session_factory, "u2").transaction() as uow:
        page = uow.messages.read_multi(filters={"thread_id": "r1"})
    assert page.results == []
