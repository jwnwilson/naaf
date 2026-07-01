from adapters.dispatcher.cursor_store import SqlSubscriberCursorStore
from interactors.dispatcher.subscriber import CursorState


def test_cursor_defaults_then_persists(session_factory):
    s = session_factory()
    store = SqlSubscriberCursorStore(s)
    assert store.get("notifier") == CursorState(last_global_seq=0, retries=0)
    store.save("notifier", CursorState(last_global_seq=5, retries=2))
    s.commit()
    assert store.get("notifier") == CursorState(last_global_seq=5, retries=2)
    store.save("notifier", CursorState(last_global_seq=9, retries=0))  # upsert
    s.commit()
    assert store.get("notifier").last_global_seq == 9
