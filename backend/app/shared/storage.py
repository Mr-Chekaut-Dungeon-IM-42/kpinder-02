import uuid
from abc import ABC, abstractmethod

import anyio
import boto3
from botocore.exceptions import BotoCoreError, ClientError
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
        """Store the photo bytes and return its object key (not a URL —
        the bucket is private; callers resolve a viewable URL via get_url)."""

    @abstractmethod
    async def get_url(self, key: str) -> str:
        """Return a short-lived, signed URL for viewing the object at `key`."""


class R2PhotoStorage(PhotoStorage):
    def __init__(self) -> None:
        if not (
            settings.r2_account_id
            and settings.r2_access_key_id
            and settings.r2_secret_access_key
            and settings.r2_bucket_name
        ):
            raise RuntimeError(
                "R2 credentials are not configured (R2_ACCOUNT_ID, "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME)"
            )
        self._bucket = settings.r2_bucket_name
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

    def _presign(self, key: str) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=settings.r2_presigned_url_ttl_seconds,
        )

    async def upload(self, data: bytes, content_type: str) -> str:
        key = f"{uuid.uuid4()}.{_EXTENSIONS[content_type]}"
        try:
            await anyio.to_thread.run_sync(self._put_object, key, data, content_type)
        except (BotoCoreError, ClientError) as exc:
            # Never leak the underlying R2/transport error to the client —
            # same "generic 503, no internal detail" pattern as the DB
            # failure handler (spec.md §3). This also keeps the response
            # inside FastAPI's normal exception-handling middleware (CORS
            # headers still apply), unlike letting it propagate unhandled.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Photo storage is unavailable",
            ) from exc
        return key

    async def get_url(self, key: str) -> str:
        try:
            # generate_presigned_url signs locally (HMAC), no network call —
            # safe to call directly without anyio.to_thread.
            return self._presign(key)
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Photo storage is unavailable",
            ) from exc


async def resolve_photo_url(storage: PhotoStorage, key: str | None) -> str | None:
    if key is None:
        return None
    return await storage.get_url(key)


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
