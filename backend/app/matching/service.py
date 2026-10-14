import base64
import json
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching import repository
from app.matching.schemas import (
    CandidateResponse,
    MatchesPage,
    MatchResponse,
    MatchUser,
    SwipeRequest,
    SwipeResponse,
)
from app.shared.config import settings
from app.shared.models import User
from app.shared.storage import get_photo_storage, resolve_photo_url


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


async def _to_candidate(user: User) -> CandidateResponse:
    photo_url = None
    if user.photo_key is not None:
        photo_url = await resolve_photo_url(get_photo_storage(), user.photo_key)
    return CandidateResponse(
        id=user.id,
        name=user.name,
        age=user.age,
        bio=user.bio,
        photo_url=photo_url,
        interests=[ui.interest.name for ui in user.interests],
    )


async def get_feed(db: AsyncSession, caller_id: uuid.UUID) -> list[CandidateResponse]:
    caller = await repository.get_user_with_interests(db, caller_id)
    if caller is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if caller.location is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Set your location before viewing the feed",
        )

    caller_interests = {ui.interest.name for ui in caller.interests}
    candidates = await repository.get_candidates(
        db, caller, settings.matching_radius_km, limit=500
    )

    def score(candidate: User) -> float:
        candidate_interests = {ui.interest.name for ui in candidate.interests}
        return _jaccard(caller_interests, candidate_interests)

    scored = sorted(candidates, key=score, reverse=True)
    return [await _to_candidate(c) for c in scored[: settings.matching_feed_size]]


async def swipe(
    db: AsyncSession, caller_id: uuid.UUID, data: SwipeRequest
) -> SwipeResponse:
    if data.target_id == caller_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot swipe on yourself",
        )
    if not await repository.user_exists(db, data.target_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    try:
        await repository.create_swipe(db, caller_id, data.target_id, data.decision)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        existing = await repository.get_swipe(db, caller_id, data.target_id)
        if existing is None or existing.decision != data.decision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Swipe decision already recorded and cannot be changed",
            ) from exc
        match = await repository.get_match_between(db, caller_id, data.target_id)
        return SwipeResponse(
            matched=match is not None, match_id=match.id if match else None
        )

    if data.decision == "pass":
        return SwipeResponse(matched=False)

    reciprocal = await repository.get_swipe(db, data.target_id, caller_id)
    if reciprocal is None or reciprocal.decision != "like":
        return SwipeResponse(matched=False)

    try:
        match = await repository.create_match(db, caller_id, data.target_id)
        await db.commit()
        return SwipeResponse(matched=True, match_id=match.id)
    except IntegrityError:
        await db.rollback()
        match = await repository.get_match_between(db, caller_id, data.target_id)
        return SwipeResponse(matched=True, match_id=match.id if match else None)


def _encode_cursor(created_at: datetime, match_id: uuid.UUID) -> str:
    payload = json.dumps({"created_at": created_at.isoformat(), "id": str(match_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["created_at"]), uuid.UUID(payload["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid cursor"
        ) from exc


async def get_matches(
    db: AsyncSession, caller_id: uuid.UUID, cursor: str | None, limit: int = 20
) -> MatchesPage:
    cursor_created_at, cursor_id = (None, None)
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_cursor(cursor)

    matches = await repository.get_matches_page(
        db, caller_id, cursor_created_at, cursor_id, limit
    )

    other_ids = [
        m.user_b_id if m.user_a_id == caller_id else m.user_a_id for m in matches
    ]
    users = await repository.get_users_by_ids(db, other_ids)

    items = []
    for m in matches:
        other = users.get(m.user_b_id if m.user_a_id == caller_id else m.user_a_id)
        if other is None:
            continue
        photo_url = None
        if other.photo_key is not None:
            photo_url = await resolve_photo_url(get_photo_storage(), other.photo_key)
        items.append(
            MatchResponse(
                match_id=m.id,
                created_at=m.created_at,
                other_user=MatchUser(id=other.id, name=other.name, photo_url=photo_url),
            )
        )

    next_cursor = None
    if len(matches) == limit:
        last = matches[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return MatchesPage(items=items, next_cursor=next_cursor)
