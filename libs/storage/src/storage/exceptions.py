class StorageError(Exception):
    """Base error for the storage lib."""


class StorageNotFound(StorageError):
    """Raised when a requested key does not exist."""
