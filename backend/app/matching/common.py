import base64
import json
import uuid
from datetime import datetime

from fastapi import HTTPException, status

from app.matching.schemas import CandidateResponse
from app.shared.models import User
from app.shared.storage import PhotoStorage, get_photo_storage, resolve_photo_url


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


async def to_candidate(
    user: User, storage: PhotoStorage | None = None
) -> CandidateResponse:
    photo_url = None
    if user.photo_key is not None:
        storage = storage or get_photo_storage()
        photo_url = await resolve_photo_url(storage, user.photo_key)
    return CandidateResponse(
        id=user.id,
        name=user.name,
        age=user.age,
        bio=user.bio,
        photo_url=photo_url,
        interests=[ui.interest.name for ui in user.interests],
    )


def encode_cursor(created_at: datetime, match_id: uuid.UUID) -> str:
    payload = json.dumps({"created_at": created_at.isoformat(), "id": str(match_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["created_at"]), uuid.UUID(payload["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid cursor"
        ) from exc
