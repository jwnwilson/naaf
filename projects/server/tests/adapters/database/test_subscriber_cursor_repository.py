from adapters.database.repositories import SubscriberCursorRepository
from interactors.dispatcher.subscriber import CursorState


def test_cursor_defaults_then_persists(session_factory):
    # Arrange
    s = session_factory()
    repo = SubscriberCursorRepository(s)

    # Act / Assert — default state
    assert repo.get("notifier") == CursorState(last_global_seq=0, retries=0)

    # Act — save and read back
    repo.save("notifier", CursorState(last_global_seq=5, retries=2))
    s.commit()
    assert repo.get("notifier") == CursorState(last_global_seq=5, retries=2)

    # Act — upsert (overwrite same key)
    repo.save("notifier", CursorState(last_global_seq=9, retries=0))
    s.commit()
    assert repo.get("notifier").last_global_seq == 9
