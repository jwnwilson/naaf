from domain.messaging.question import (
    APPROVE_REJECT,
    is_valid_option,
    question_payload,
    resolve_payload,
)


def test_question_payload_carries_options_and_run_link():
    p = question_payload(run_id="run1", gate_kind="plan")
    assert p["options"] == APPROVE_REJECT
    assert p["run_id"] == "run1"
    assert p["gate_kind"] == "plan"
    assert p["resolved_option"] is None


def test_resolve_payload_is_immutable_and_sets_option():
    p = question_payload(run_id="run1", gate_kind="plan")
    resolved = resolve_payload(p, "approve")
    assert resolved["resolved_option"] == "approve"
    assert p["resolved_option"] is None  # original untouched


def test_is_valid_option():
    p = question_payload(run_id="run1", gate_kind="plan")
    assert is_valid_option(p, "approve") is True
    assert is_valid_option(p, "reject") is True
    assert is_valid_option(p, "banana") is False
