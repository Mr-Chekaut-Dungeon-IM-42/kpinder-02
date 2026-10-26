from matching_core.errors import CallerNotFoundError, LocationRequiredError
from matching_core.models import FeedCandidate
from matching_core.ports import CandidateRepository, PhotoUrlResolver
from matching_core.scoring import jaccard

DEFAULT_CANDIDATE_FETCH_LIMIT = 500


class FeedService:
    """Candidate selection + interest-overlap ranking.

    Extracted from app/matching/queries.py's GetFeedQuery (Lab 5) — moved
    as-is behaviorally (same default candidate_fetch_limit, same ranking),
    with its DB/storage dependencies replaced by the ports above. See
    ai/audit/lab-5.md for the load-test data that singled this module out
    and standards/adr/0026 for the port/DI design.
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

        results: list[FeedCandidate] = []
        for score, candidate in scored[:feed_size]:
            photo_url = None
            if candidate.photo_key is not None and self._photo_resolver is not None:
                photo_url = await self._photo_resolver.resolve(candidate.photo_key)
            results.append(
                FeedCandidate(
                    id=candidate.id,
                    name=candidate.name,
                    age=candidate.age,
                    bio=candidate.bio,
                    photo_url=photo_url,
                    interests=sorted(candidate.interests),
                    score=score,
                )
            )
        return results
