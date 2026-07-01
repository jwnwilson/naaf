from domain.base import utcnow
from interactors.dispatcher.subscriber import CursorState
from sqlalchemy.orm import Session

from adapters.database.orm import SubscriberCursorRow


class SqlSubscriberCursorStore:
    def __init__(self, session: Session):
        self.session = session

    def get(self, name: str) -> CursorState:
        row = self.session.get(SubscriberCursorRow, name)
        if row is None:
            return CursorState()
        return CursorState(last_global_seq=row.last_global_seq, retries=row.retries)

    def save(self, name: str, state: CursorState) -> None:
        row = self.session.get(SubscriberCursorRow, name)
        if row is None:
            row = SubscriberCursorRow(name=name)
            self.session.add(row)
        row.last_global_seq = state.last_global_seq
        row.retries = state.retries
        row.updated_at = utcnow()
        self.session.flush()
