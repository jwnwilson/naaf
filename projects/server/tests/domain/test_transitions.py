import pytest

from domain.errors import InvalidTransition
from domain.transitions import validate_transition
from domain.work_item import WorkItemStatus as S


def test_forward_flow_is_allowed():
    assert validate_transition(S.BACKLOG, S.TODO) is S.TODO
    assert validate_transition(S.TODO, S.IN_PROGRESS) is S.IN_PROGRESS
    assert validate_transition(S.IN_PROGRESS, S.IN_REVIEW) is S.IN_REVIEW
    assert validate_transition(S.IN_REVIEW, S.DONE) is S.DONE


def test_review_can_bounce_back_to_in_progress():
    assert validate_transition(S.IN_REVIEW, S.IN_PROGRESS) is S.IN_PROGRESS


def test_can_move_back_to_backlog_from_todo():
    assert validate_transition(S.TODO, S.BACKLOG) is S.BACKLOG


def test_illegal_skip_raises():
    with pytest.raises(InvalidTransition):
        validate_transition(S.BACKLOG, S.DONE)


def test_done_is_terminal():
    with pytest.raises(InvalidTransition):
        validate_transition(S.DONE, S.IN_PROGRESS)


def test_same_status_is_rejected():
    with pytest.raises(InvalidTransition):
        validate_transition(S.TODO, S.TODO)
