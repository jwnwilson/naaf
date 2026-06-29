from domain.errors import InvalidTransition
from domain.work_item import WorkItemStatus as S

# Directed edges of the work-item lifecycle. blocked/failed are reachable from any
# active state; blocked resumes to in_progress; failed and done are terminal.
ALLOWED_TRANSITIONS: dict[S, set[S]] = {
    S.TO_DO: {S.IN_PROGRESS, S.BLOCKED, S.FAILED},
    S.IN_PROGRESS: {S.IN_REVIEW, S.BLOCKED, S.FAILED},
    S.IN_REVIEW: {S.IN_PROGRESS, S.APPROVED, S.BLOCKED, S.FAILED},
    S.APPROVED: {S.DONE, S.IN_PROGRESS, S.BLOCKED, S.FAILED},
    S.BLOCKED: {S.IN_PROGRESS, S.FAILED},
    S.DONE: set(),
    S.FAILED: set(),
}


def validate_transition(current: S, target: S) -> S:
    """Return target if the current->target edge is legal, else raise."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(
            f"Cannot transition from {current.value} to {target.value}"
        )
    return target
