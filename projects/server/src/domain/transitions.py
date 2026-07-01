from domain.errors import InvalidTransition
from domain.work_item import WorkItemStatus as S

# Directed edges of the work-item lifecycle (UI-canonical 5-state set).
ALLOWED_TRANSITIONS: dict[S, set[S]] = {
    S.BACKLOG: {S.TODO},
    S.TODO: {S.BACKLOG, S.IN_PROGRESS},
    S.IN_PROGRESS: {S.IN_REVIEW, S.TODO, S.DONE},
    S.IN_REVIEW: {S.IN_PROGRESS, S.DONE},
    S.DONE: set(),
}


def validate_transition(current: S, target: S) -> S:
    """Return target if the current->target edge is legal, else raise."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(
            f"Cannot transition from {current.value} to {target.value}"
        )
    return target
