import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching import repository
from app.matching.common import decode_cursor, encode_cursor, jaccard, to_candidate
from app.matching.schemas import (
    CandidateResponse,
    MatchesPage,
    MatchResponse,
    MatchUser,
)
from app.shared.config import settings
from app.shared.db import get_db
from app.shared.models import User
from app.shared.storage import PhotoStorage, get_photo_storage, resolve_photo_url


class GetFeedQuery:
    def __init__(self, db: AsyncSession, storage: PhotoStorage | None = None) -> None:
        self.db = db
        self.storage = storage

    async def execute(self, caller_id: uuid.UUID) -> list[CandidateResponse]:
        caller = await repository.get_user_with_interests(self.db, caller_id)
        if caller is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )
        if caller.location is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Set your location before viewing the feed",
            )

        caller_interests = {ui.interest.name for ui in caller.interests}
        candidates = await repository.get_candidates(
            self.db, caller, settings.matching_radius_km, limit=500
        )

        def score(candidate: User) -> float:
            candidate_interests = {ui.interest.name for ui in candidate.interests}
            return jaccard(caller_interests, candidate_interests)

        scored = sorted(candidates, key=score, reverse=True)
        return [
            await to_candidate(c, storage=self.storage)
            for c in scored[: settings.matching_feed_size]
        ]


class GetMatchesQuery:
    def __init__(self, db: AsyncSession, storage: PhotoStorage | None = None) -> None:
        self.db = db
        self.storage = storage

    async def execute(
        self, caller_id: uuid.UUID, cursor: str | None, limit: int = 20
    ) -> MatchesPage:
        cursor_created_at, cursor_id = (None, None)
        if cursor is not None:
            cursor_created_at, cursor_id = decode_cursor(cursor)

        matches = await repository.get_matches_page(
            self.db, caller_id, cursor_created_at, cursor_id, limit
        )

        other_ids = [
            m.user_b_id if m.user_a_id == caller_id else m.user_a_id for m in matches
        ]
        users = await repository.get_users_by_ids(self.db, other_ids)

        items = []
        storage = self.storage
        for m in matches:
            other = users.get(m.user_b_id if m.user_a_id == caller_id else m.user_a_id)
            if other is None:
                continue
            photo_url = None
            if other.photo_key is not None:
                if storage is None:
                    storage = get_photo_storage()
                photo_url = await resolve_photo_url(storage, other.photo_key)
            items.append(
                MatchResponse(
                    match_id=m.id,
                    created_at=m.created_at,
                    other_user=MatchUser(
                        id=other.id, name=other.name, photo_url=photo_url
                    ),
                )
            )

        next_cursor = None
        if len(matches) == limit:
            last = matches[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        return MatchesPage(items=items, next_cursor=next_cursor)


def get_feed_query(db: AsyncSession = Depends(get_db)) -> GetFeedQuery:
    return GetFeedQuery(db=db)


def get_matches_query(db: AsyncSession = Depends(get_db)) -> GetMatchesQuery:
    return GetMatchesQuery(db=db)
