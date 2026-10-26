"""Concrete adapters satisfying matching_core's ports (standards/adr/0026).

This is the only file in the matching slice allowed to know both
matching_core's Protocols *and* this app's SQLAlchemy/storage internals —
everything else either stays on one side of the boundary or the other.
"""

import uuid

from matching_core import CallerProfile, CandidateProfile
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching import repository
from app.shared.models import User
from app.shared.storage import PhotoStorage, get_photo_storage, resolve_photo_url


def _to_caller_profile(user: User) -> CallerProfile:
    return CallerProfile(
        id=str(user.id),
        gender=user.gender,
        seeking=user.seeking,
        age_min=user.age_min,
        age_max=user.age_max,
        has_location=user.location is not None,
        interests=frozenset(ui.interest.name for ui in user.interests),
    )


def _to_candidate_profile(user: User) -> CandidateProfile:
    return CandidateProfile(
        id=str(user.id),
        name=user.name,
        age=user.age,
        bio=user.bio,
        photo_key=user.photo_key,
        interests=frozenset(ui.interest.name for ui in user.interests),
    )


class SqlAlchemyCandidateRepository:
    """Implements matching_core.ports.CandidateRepository against this app's
    `User`/`UserInterest` tables — the only place the SQLAlchemy query from
    the old GetFeedQuery lives now."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        # One repository instance is wired per request (see get_feed_query
        # below), so a single cached caller User is all get_candidates below
        # ever needs — it always follows the one get_caller call for the
        # same request.
        self._caller_user: User | None = None

    async def get_caller(self, caller_id: str) -> CallerProfile | None:
        user = await repository.get_user_with_interests(self._db, uuid.UUID(caller_id))
        if user is None:
            return None
        self._caller_user = user
        return _to_caller_profile(user)

    async def get_candidates(
        self, caller: CallerProfile, radius_km: float, limit: int
    ) -> list[CandidateProfile]:
        assert self._caller_user is not None and str(self._caller_user.id) == caller.id
        candidates = await repository.get_candidates(
            self._db, self._caller_user, radius_km, limit=limit
        )
        return [_to_candidate_profile(c) for c in candidates]


class StoragePhotoUrlResolver:
    """Implements matching_core.ports.PhotoUrlResolver against this app's
    PhotoStorage (R2) — lazily instantiated so a feed request with no
    photos never touches R2 config at all."""

    def __init__(self, storage: PhotoStorage | None = None) -> None:
        self._storage = storage

    async def resolve(self, photo_key: str) -> str | None:
        storage = self._storage or get_photo_storage()
        return await resolve_photo_url(storage, photo_key)
