class RecordNotFound(Exception):
    """Raised when a row is not found (or is out of the caller's owner scope)."""


class IntegrityConflict(Exception):
    """Raised on a DB integrity violation (unique/FK)."""
