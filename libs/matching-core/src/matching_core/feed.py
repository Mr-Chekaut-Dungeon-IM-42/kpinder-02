import asyncio

from matching_core.errors import CallerNotFoundError, LocationRequiredError
from matching_core.models import CandidateProfile, FeedCandidate
from matching_core.ports import CandidateRepository, PhotoUrlResolver
from matching_core.scoring import jaccard

DEFAULT_CANDIDATE_FETCH_LIMIT = 50


class FeedService:
    """Candidate selection + interest-overlap ranking.

    Extracted from app/matching/queries.py's GetFeedQuery (Lab 5), with its
    DB/storage dependencies replaced by the ports above. Behavior-preserving
    except for one thing: photo URL resolution for the returned candidates
    is now concurrent (asyncio.gather), not sequential — see
    ai/audit/lab-5.md's "secondary finding" for why that mattered. See
    standards/adr/0026 for the port/DI design.
    """

    def __init__(
        self,
        repository: CandidateRepository,
        photo_resolver: PhotoUrlResolver | None = None,
    ) -> None:
        self._repository = repository
        self._photo_resolver = photo_resolver

    async def get_feed(
        self,
        caller_id: str,
        *,
        radius_km: float,
        feed_size: int,
        candidate_fetch_limit: int = DEFAULT_CANDIDATE_FETCH_LIMIT,
    ) -> list[FeedCandidate]:
        caller = await self._repository.get_caller(caller_id)
        if caller is None:
            raise CallerNotFoundError(caller_id)
        if not caller.has_location:
            raise LocationRequiredError(caller_id)

        candidates = await self._repository.get_candidates(
            caller, radius_km, limit=candidate_fetch_limit
        )

        scored = sorted(
            ((jaccard(caller.interests, c.interests), c) for c in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )

        top = scored[:feed_size]

        async def _resolve_photo(candidate: CandidateProfile) -> str | None:
            if candidate.photo_key is None or self._photo_resolver is None:
                return None
            return await self._photo_resolver.resolve(candidate.photo_key)

        # Concurrent, not sequential: N candidates with photos used to mean
        # N round-trips awaited one after another (ai/audit/lab-5.md's
        # "secondary finding", fixed here) — gather runs them all at once,
        # so the wall-clock cost is one round-trip, not N.
        photo_urls = await asyncio.gather(*(_resolve_photo(c) for _, c in top))

        return [
            FeedCandidate(
                id=candidate.id,
                name=candidate.name,
                age=candidate.age,
                bio=candidate.bio,
                photo_url=photo_url,
                interests=sorted(candidate.interests),
                score=score,
            )
            for (score, candidate), photo_url in zip(top, photo_urls, strict=True)
        ]
