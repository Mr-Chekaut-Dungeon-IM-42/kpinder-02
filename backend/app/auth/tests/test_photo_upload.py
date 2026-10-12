import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.auth import service
from app.shared.models import User

JPEG_BYTES = b"\xff\xd8\xff" + b"rest-of-jpeg"


def _user() -> User:
    user = User(id=uuid.uuid4(), email="a@b.com", password_hash="x", name="Alice")
    user.interests = []
    return user


def _file(data: bytes, content_type: str) -> MagicMock:
    file = MagicMock()
    file.read = AsyncMock(return_value=data)
    file.content_type = content_type
    return file


@pytest.mark.asyncio
async def test_upload_photo_success():
    db = AsyncMock()
    user = _user()
    file = _file(JPEG_BYTES, "image/jpeg")
    storage = AsyncMock()
    storage.upload.return_value = "abc123.jpg"

    with patch("app.auth.service.repository.get_user_by_id", return_value=user):
        result = await service.upload_photo(db, user.id, file, storage)

    assert result.photo_key == "abc123.jpg"
    storage.upload.assert_awaited_once_with(JPEG_BYTES, "image/jpeg")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_photo_wrong_content_type_raises_415():
    db = AsyncMock()
    user = _user()
    file = _file(b"not an image", "text/plain")
    storage = AsyncMock()

    with (
        patch("app.auth.service.repository.get_user_by_id", return_value=user),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.upload_photo(db, user.id, file, storage)

    assert exc_info.value.status_code == 415
    storage.upload.assert_not_awaited()
