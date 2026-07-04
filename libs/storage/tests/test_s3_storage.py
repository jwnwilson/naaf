import importlib.util

import pytest

boto3_missing = importlib.util.find_spec("boto3") is None
pytestmark = pytest.mark.skipif(boto3_missing, reason="boto3 (s3 extra) not installed")


def test_s3_storage_is_importable_and_constructs():
    from storage import S3Storage

    store = S3Storage(bucket="naaf-test", region="eu-west-1")
    assert store.local_path("work-item/abc/x.txt").endswith("work-item/abc/x.txt")


def test_get_missing_maps_to_storage_not_found(monkeypatch):
    import botocore.exceptions

    from storage import S3Storage, StorageNotFound

    store = S3Storage(bucket="naaf-test", region="eu-west-1")

    class _FakeClient:
        def get_object(self, **_):
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey"}}, "GetObject"
            )

    monkeypatch.setattr(store, "_client", _FakeClient())
    with pytest.raises(StorageNotFound):
        store.get_bytes("work-item/abc/missing.txt")
