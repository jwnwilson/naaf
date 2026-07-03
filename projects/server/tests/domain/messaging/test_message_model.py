from domain.messaging.message import AuthorKind, Message, MessageKind


def test_message_defaults_to_user_text():
    msg = Message(owner_id="o", thread_id="wi1", content="hello")
    assert msg.author_kind is AuthorKind.USER
    assert msg.kind is MessageKind.TEXT
    assert msg.author_role is None
    assert msg.mentions == []
    assert msg.payload == {}
    assert msg.run_id is None


def test_agent_message_carries_role_and_model():
    msg = Message(
        owner_id="o", thread_id="wi1", author_kind=AuthorKind.AGENT,
        author_role="backend", model_alias="claude-opus-4",
        kind=MessageKind.FILE_WRITE, content="wrote refresh.py",
        payload={"path": "src/auth/refresh.py", "lines": 84},
    )
    assert msg.author_role == "backend"
    assert msg.model_alias == "claude-opus-4"
    assert msg.payload["path"] == "src/auth/refresh.py"
