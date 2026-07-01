# Re-export for backward compatibility — implementation moved to adapters/database/repositories.py.
# This module will be deleted in Task 7 when the dispatcher package is removed.
from adapters.database.repositories import SubscriberCursorRepository as SqlSubscriberCursorStore

__all__ = ["SqlSubscriberCursorStore"]
