import pytest
from domain.errors import InvalidTransition
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus as S


def test_forward_flow_is_allowed():
    assert validate_transition(S.TO_DO, S.IN_PROGRESS) is S.IN_PROGRESS
    assert validate_transition(S.IN_PROGRESS, S.IN_REVIEW) is S.IN_REVIEW
    assert validate_transition(S.IN_REVIEW, S.APPROVED) is S.APPROVED
    assert validate_transition(S.APPROVED, S.DONE) is S.DONE


def test_review_can_bounce_back_to_in_progress():
    assert validate_transition(S.IN_REVIEW, S.IN_PROGRESS) is S.IN_PROGRESS


def test_any_active_status_can_block_and_unblock():
    assert validate_transition(S.IN_PROGRESS, S.BLOCKED) is S.BLOCKED
    assert validate_transition(S.BLOCKED, S.IN_PROGRESS) is S.IN_PROGRESS


def test_illegal_skip_raises():
    with pytest.raises(InvalidTransition):
        validate_transition(S.TO_DO, S.DONE)


def test_done_is_terminal():
    with pytest.raises(InvalidTransition):
        validate_transition(S.DONE, S.IN_PROGRESS)


def test_same_status_is_rejected():
    with pytest.raises(InvalidTransition):
        validate_transition(S.TO_DO, S.TO_DO)
