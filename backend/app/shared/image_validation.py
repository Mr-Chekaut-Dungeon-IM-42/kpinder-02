from fastapi import HTTPException, status

MAX_PHOTO_BYTES = 5 * 1024 * 1024

_MAGIC_BYTES: dict[str, bytes] = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}
_ALLOWED_CONTENT_TYPES = {*_MAGIC_BYTES, "image/webp"}


def _is_webp(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def validate_image(data: bytes, content_type: str) -> None:
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {content_type}",
        )

    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Photo exceeds the 5MB size limit",
        )

    magic = _MAGIC_BYTES.get(content_type)
    matches_magic = data.startswith(magic) if magic else _is_webp(data)
    if not matches_magic:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content does not match its declared content type",
        )
