from typing import Protocol

from matching_core.models import CallerProfile, CandidateProfile


class CandidateRepository(Protocol):
    """The only thing FeedService knows about storage: these two methods.

    No SQLAlchemy/asyncpg type appears anywhere in this file — an adapter
    (e.g. backend/app/matching/adapters.py) implements this against whatever
    the caller's infra actually is.
    """

    async def get_caller(self, caller_id: str) -> CallerProfile | None: ...

    async def get_candidates(
        self, caller: CallerProfile, radius_km: float, limit: int
    ) -> list[CandidateProfile]: ...


class PhotoUrlResolver(Protocol):
    async def resolve(self, photo_key: str) -> str | None: ...
