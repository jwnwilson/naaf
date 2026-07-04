import pytest
from storage import LocalStorage, StorageNotFound


def test_put_then_get_round_trips_bytes(tmp_path):
    store = LocalStorage(str(tmp_path))
    store.put_bytes("work-item/abc/hello.txt", b"hi there")
    assert store.get_bytes("work-item/abc/hello.txt") == b"hi there"


def test_exists_reflects_presence(tmp_path):
    store = LocalStorage(str(tmp_path))
    assert store.exists("work-item/abc/x.png") is False
    store.put_bytes("work-item/abc/x.png", b"\x89PNG")
    assert store.exists("work-item/abc/x.png") is True


def test_list_returns_keys_under_prefix(tmp_path):
    store = LocalStorage(str(tmp_path))
    store.put_bytes("work-item/abc/a.txt", b"a")
    store.put_bytes("work-item/abc/b.txt", b"b")
    store.put_bytes("work-item/other/c.txt", b"c")
    assert sorted(store.list("work-item/abc/")) == ["work-item/abc/a.txt", "work-item/abc/b.txt"]


def test_delete_removes_key(tmp_path):
    store = LocalStorage(str(tmp_path))
    store.put_bytes("work-item/abc/a.txt", b"a")
    store.delete("work-item/abc/a.txt")
    assert store.exists("work-item/abc/a.txt") is False


def test_get_missing_raises_storage_not_found(tmp_path):
    store = LocalStorage(str(tmp_path))
    with pytest.raises(StorageNotFound):
        store.get_bytes("work-item/abc/missing.txt")


def test_key_escaping_the_root_is_rejected(tmp_path):
    store = LocalStorage(str(tmp_path))
    with pytest.raises(ValueError):
        store.put_bytes("../escape.txt", b"nope")


def test_empty_key_is_rejected(tmp_path):
    store = LocalStorage(str(tmp_path))
    with pytest.raises(ValueError):
        store.put_bytes("", b"nope")
