from adapters.agent.chat.echo import EchoChatResponder
from domain.messaging.chat import ChatTurn


def test_echo_responds_with_role_ack():
    r = EchoChatResponder()
    out = r.respond("backend", [ChatTurn(role="user", content="hi")], "My Task")
    assert out == "[backend] ack"


def test_echo_can_mention_a_partner_for_fanout_tests():
    r = EchoChatResponder(mention="qa")
    out = r.respond("backend", [], "My Task")
    assert "@qa" in out
