from adapters.storage.factory import build_storage
from adapters.storage.keys import attachment_key, attachment_prefix
from interactors.api.settings import Settings
from storage import LocalStorage, S3Storage


def test_key_convention():
    assert attachment_key("wi123", "a.png") == "work-item/wi123/a.png"
    assert attachment_prefix("wi123") == "work-item/wi123/"


def test_build_storage_defaults_to_local(tmp_path):
    settings = Settings(attachments_root=str(tmp_path))
    store = build_storage(settings)
    assert isinstance(store, LocalStorage)
    store.put_bytes(attachment_key("wi1", "x.txt"), b"y")
    assert store.get_bytes("work-item/wi1/x.txt") == b"y"


def test_build_storage_s3_backend_returns_s3storage():
    settings = Settings(storage_backend="s3", s3_bucket="b", s3_region="eu-west-1")
    store = build_storage(settings)
    assert isinstance(store, S3Storage)
