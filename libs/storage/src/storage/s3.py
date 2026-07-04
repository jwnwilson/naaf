from .exceptions import StorageError, StorageNotFound
from .ports import Storage


class S3Storage(Storage):
    """S3-backed blob store. boto3 is imported lazily so the base install stays lean.

    `local_path` returns a path under a scratch dir; it is only meaningful after a
    sync-down (a cloud-deployment concern) and is not used by the local default.
    """

    def __init__(self, bucket: str, region: str, prefix: str = "") -> None:
        self._bucket = bucket
        self._region = region
        self._prefix = prefix.rstrip("/")
        self.__client = None

    @property
    def _client(self):
        if self.__client is None:
            import boto3

            self.__client = boto3.client("s3", region_name=self._region)
        return self.__client

    @_client.setter
    def _client(self, value) -> None:
        self.__client = value

    def _full(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=self._full(key), Body=data, **extra)

    def get_bytes(self, key: str) -> bytes:
        import botocore.exceptions

        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=self._full(key))
        except botocore.exceptions.ClientError as err:
            code = err.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise StorageNotFound(key) from err
            raise StorageError(str(err)) from err
        return resp["Body"].read()

    def list(self, prefix: str) -> list[str]:
        resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=self._full(prefix))
        keys = [obj["Key"] for obj in resp.get("Contents", [])]
        if self._prefix:
            keys = [k[len(self._prefix) + 1 :] for k in keys]
        return sorted(keys)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._full(key))

    def exists(self, key: str) -> bool:
        import botocore.exceptions

        try:
            self._client.head_object(Bucket=self._bucket, Key=self._full(key))
            return True
        except botocore.exceptions.ClientError as err:
            if err.response["Error"]["Code"] in ("404", "NoSuchKey", "NoSuchBucket"):
                return False
            raise StorageError(str(err)) from err

    def local_path(self, key: str) -> str:
        return f"/tmp/naaf-s3-cache/{self._full(key)}"
