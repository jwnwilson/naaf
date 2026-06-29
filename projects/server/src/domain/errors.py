class DomainError(Exception):
    """Base class for all domain-level errors."""


class RecordNotFound(DomainError):
    """A requested record does not exist (or is out of the caller's owner scope)."""


class IntegrityConflict(DomainError):
    """A persistence constraint (unique/FK) was violated."""


class InvalidTransition(DomainError):
    """A status change is not allowed by the state machine."""


class InvalidHierarchy(DomainError):
    """A work-item parent/child relationship is not allowed."""
