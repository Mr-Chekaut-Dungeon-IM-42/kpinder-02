import pytest
from fastapi import HTTPException

from app.shared.image_validation import MAX_PHOTO_BYTES, validate_image

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBP"


def test_valid_jpeg_passes():
    validate_image(JPEG_MAGIC + b"rest", "image/jpeg")


def test_valid_png_passes():
    validate_image(PNG_MAGIC + b"rest", "image/png")


def test_valid_webp_passes():
    validate_image(WEBP_BYTES, "image/webp")


def test_unsupported_content_type_raises_415():
    with pytest.raises(HTTPException) as exc_info:
        validate_image(b"hello", "text/plain")
    assert exc_info.value.status_code == 415


def test_mismatched_magic_bytes_raises_415():
    with pytest.raises(HTTPException) as exc_info:
        validate_image(b"not actually a jpeg", "image/jpeg")
    assert exc_info.value.status_code == 415


def test_oversize_raises_413():
    oversized = JPEG_MAGIC + b"\x00" * MAX_PHOTO_BYTES
    with pytest.raises(HTTPException) as exc_info:
        validate_image(oversized, "image/jpeg")
    assert exc_info.value.status_code == 413
