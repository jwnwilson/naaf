from domain.runs.messages import MessageType, chat_recipient


def test_chat_message_type_exists():
    assert MessageType.CHAT.value == "chat"


def test_chat_recipient_is_work_item_scoped():
    assert chat_recipient("wi1", "backend") == "wi:wi1:backend"
