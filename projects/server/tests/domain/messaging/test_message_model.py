from domain.messaging.message import Message, MessageRole


def test_message_defaults_id_and_optional_agent():
    msg = Message(owner_id="u1", thread_id="r1", role=MessageRole.USER, content="hi")
    assert len(msg.id) == 32
    assert msg.agent_id is None
    assert msg.role == "user"


def test_message_is_immutable_via_model_copy():
    msg = Message(owner_id="u1", thread_id="r1", role=MessageRole.USER, content="hi")
    updated = msg.model_copy(update={"content": "bye"})
    assert msg.content == "hi"
    assert updated.content == "bye"


def test_role_values():
    assert [r.value for r in MessageRole] == ["user", "agent", "lead_agent"]
