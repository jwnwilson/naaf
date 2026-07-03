from domain.messaging.dispatch import MAX_FANOUT_DEPTH, plan_dispatch, plan_fanout
from domain.runs.messages import MessageType, chat_recipient


def test_chat_message_type_exists():
    assert MessageType.CHAT.value == "chat"


def test_chat_recipient_is_work_item_scoped():
    assert chat_recipient("wi1", "backend") == "wi:wi1:backend"


def test_plan_dispatch_routes_mentions_below_cap():
    assert plan_dispatch("@backend look here", 0) == ["backend"]


def test_plan_dispatch_defaults_to_lead_below_cap():
    assert plan_dispatch("no mention", 0) == ["lead"]


def test_plan_dispatch_stops_at_the_depth_cap():
    assert plan_dispatch("@backend @qa keep going", MAX_FANOUT_DEPTH) == []
    assert plan_dispatch("@backend", MAX_FANOUT_DEPTH - 1) == ["backend"]


# plan_fanout — agent-reply fan-out: EXPLICIT mentions only, never default-to-lead.


def test_plan_fanout_honours_explicit_mentions_below_cap():
    assert plan_fanout("@qa please look", 1) == ["qa"]


def test_plan_fanout_does_not_default_to_lead():
    # An agent reply with no @mention addresses no one — no cascade.
    assert plan_fanout("[backend] ack — done, no mention", 1) == []


def test_plan_fanout_stops_at_the_depth_cap():
    assert plan_fanout("@qa", MAX_FANOUT_DEPTH) == []
    assert plan_fanout("@qa", MAX_FANOUT_DEPTH - 1) == ["qa"]
