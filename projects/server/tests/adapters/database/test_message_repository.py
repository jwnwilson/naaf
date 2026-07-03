from adapters.database.uow import SqlUnitOfWork
from domain.messaging.message import AuthorKind, Message, MessageKind


def _uow(session_factory, owner="dev-user") -> SqlUnitOfWork:
    return SqlUnitOfWork(session_factory, required_filters={"owner_id": owner})


def test_roundtrip_preserves_kind_role_mentions_payload(session_factory):
    uow = _uow(session_factory)
    with uow.transaction():
        created = uow.messages.create(Message(
            owner_id="", thread_id="wi1", author_kind=AuthorKind.AGENT,
            author_role="backend", model_alias="claude-opus-4",
            kind=MessageKind.FILE_WRITE, content="wrote it",
            mentions=["qa"], payload={"path": "src/x.py", "lines": 3},
        ))
    with uow.transaction():
        page = uow.messages.read_multi(filters={"thread_id": "wi1"}, order_by="created_at")
    got = page.results[0]
    assert got.id == created.id
    assert got.author_role == "backend"
    assert got.kind is MessageKind.FILE_WRITE
    assert got.mentions == ["qa"]
    assert got.payload == {"path": "src/x.py", "lines": 3}


def test_messages_are_owner_scoped(session_factory):
    with _uow(session_factory, "alice").transaction() as _:
        _uow(session_factory, "alice")  # noqa
    a = _uow(session_factory, "alice")
    with a.transaction():
        a.messages.create(Message(owner_id="", thread_id="wi1", content="secret"))
    b = _uow(session_factory, "bob")
    with b.transaction():
        page = b.messages.read_multi(filters={"thread_id": "wi1"})
    assert page.results == []
