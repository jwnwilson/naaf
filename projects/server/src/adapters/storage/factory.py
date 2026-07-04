import os

from interactors.api.settings import Settings
from storage import LocalStorage, S3Storage, Storage


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(bucket=settings.s3_bucket, region=settings.s3_region)
    root = os.path.expanduser(settings.attachments_root)
    return LocalStorage(root)
