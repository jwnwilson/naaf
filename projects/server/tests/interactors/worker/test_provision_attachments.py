from adapters.storage.keys import attachment_key
from interactors.worker.handlers import materialize_attachments
from storage import LocalStorage


def test_materialize_writes_attachments_into_workspace(tmp_path):
    root = tmp_path / "store"
    store = LocalStorage(str(root))
    store.put_bytes(attachment_key("wi1", "a.txt"), b"alpha")
    store.put_bytes(attachment_key("wi1", "b.png"), b"\x89PNG")

    workspace = tmp_path / "clone"
    workspace.mkdir()

    names = materialize_attachments(store, "wi1", str(workspace))

    dest = workspace / ".naaf" / "attachments"
    assert (dest / "a.txt").read_bytes() == b"alpha"
    assert (dest / "b.png").read_bytes() == b"\x89PNG"
    assert sorted(names) == ["a.txt", "b.png"]


def test_materialize_no_attachments_returns_empty(tmp_path):
    store = LocalStorage(str(tmp_path / "store"))
    workspace = tmp_path / "clone"
    workspace.mkdir()
    assert materialize_attachments(store, "wiX", str(workspace)) == []
