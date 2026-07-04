import importlib.util

import pytest

boto3_missing = importlib.util.find_spec("boto3") is None
pytestmark = pytest.mark.skipif(boto3_missing, reason="boto3 (s3 extra) not installed")


def test_s3_storage_is_importable_and_constructs():
    from storage import S3Storage

    store = S3Storage(bucket="naaf-test", region="eu-west-1")
    assert store.local_path("work-item/abc/x.txt").endswith("work-item/abc/x.txt")


def test_get_missing_maps_to_storage_not_found():
    import botocore.exceptions
    from storage import S3Storage, StorageNotFound

    store = S3Storage(bucket="naaf-test", region="eu-west-1")

    class _FakeClient:
        def get_object(self, **_):
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey"}}, "GetObject"
            )

    # Assign straight through the property setter (no getattr, so the lazy
    # getter never eagerly builds a real boto3 client). monkeypatch.setattr
    # would getattr the original first to save it, triggering that eager build.
    store._client = _FakeClient()
    with pytest.raises(StorageNotFound):
        store.get_bytes("work-item/abc/missing.txt")


def test_exists_returns_false_for_404_class_error():
    import botocore.exceptions
    from storage import S3Storage

    store = S3Storage(bucket="naaf-test", region="eu-west-1")

    class _FakeClient:
        def head_object(self, **_):
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "404"}}, "HeadObject"
            )

    store._client = _FakeClient()
    assert store.exists("work-item/abc/missing.txt") is False


def test_exists_reraises_non_404_error_as_storage_error():
    import botocore.exceptions
    from storage import S3Storage, StorageError

    store = S3Storage(bucket="naaf-test", region="eu-west-1")

    class _FakeClient:
        def head_object(self, **_):
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "AccessDenied"}}, "HeadObject"
            )

    store._client = _FakeClient()
    with pytest.raises(StorageError):
        store.exists("work-item/abc/denied.txt")
