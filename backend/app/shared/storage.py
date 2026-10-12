import uuid
from abc import ABC, abstractmethod

import anyio
import boto3
from fastapi import HTTPException, status

from app.shared.config import settings

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class PhotoStorage(ABC):
    @abstractmethod
    async def upload(self, data: bytes, content_type: str) -> str:
        """Store the photo bytes and return its public URL."""


class R2PhotoStorage(PhotoStorage):
    def __init__(self) -> None:
        if not (
            settings.r2_account_id
            and settings.r2_access_key_id
            and settings.r2_secret_access_key
            and settings.r2_bucket_name
            and settings.r2_public_base_url
        ):
            raise RuntimeError(
                "R2 credentials are not configured (R2_ACCOUNT_ID, "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, "
                "R2_PUBLIC_BASE_URL)"
            )
        self._bucket = settings.r2_bucket_name
        self._public_base_url = settings.r2_public_base_url.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )

    def _put_object(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )

    async def upload(self, data: bytes, content_type: str) -> str:
        key = f"{uuid.uuid4()}.{_EXTENSIONS[content_type]}"
        await anyio.to_thread.run_sync(self._put_object, key, data, content_type)
        return f"{self._public_base_url}/{key}"


_storage: PhotoStorage | None = None


def get_photo_storage() -> PhotoStorage:
    global _storage
    if _storage is None:
        try:
            _storage = R2PhotoStorage()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Photo storage is not configured",
            ) from exc
    return _storage
