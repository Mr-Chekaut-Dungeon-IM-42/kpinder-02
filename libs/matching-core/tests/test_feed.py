import asyncio

import pytest

from matching_core.errors import CallerNotFoundError, LocationRequiredError
from matching_core.feed import FeedService
from matching_core.models import CallerProfile, CandidateProfile


class FakeRepository:
    """In-memory fake — no DB, no network. This is the point of the port
    boundary: FeedService never knows this isn't SQLAlchemy."""

    def __init__(
        self,
        caller: CallerProfile | None,
        candidates: list[CandidateProfile],
    ) -> None:
        self._caller = caller
        self._candidates = candidates
        self.last_limit: int | None = None

    async def get_caller(self, caller_id: str) -> CallerProfile | None:
        return self._caller

    async def get_candidates(
        self, caller: CallerProfile, radius_km: float, limit: int
    ) -> list[CandidateProfile]:
        self.last_limit = limit
        return self._candidates[:limit]


class FakePhotoResolver:
    def __init__(self, urls: dict[str, str]) -> None:
        self._urls = urls

    async def resolve(self, photo_key: str) -> str | None:
        return self._urls.get(photo_key)


@pytest.mark.asyncio
async def test_unknown_caller_raises_typed_error(make_caller):
    service = FeedService(repository=FakeRepository(caller=None, candidates=[]))
    with pytest.raises(CallerNotFoundError):
        await service.get_feed("missing", radius_km=50.0, feed_size=20)


@pytest.mark.asyncio
async def test_caller_without_location_raises_typed_error(make_caller):
    caller = make_caller(has_location=False)
    service = FeedService(repository=FakeRepository(caller=caller, candidates=[]))
    with pytest.raises(LocationRequiredError):
        await service.get_feed(caller.id, radius_km=50.0, feed_size=20)


@pytest.mark.asyncio
async def test_ranks_by_interest_overlap(make_caller, make_candidate):
    caller = make_caller(interests=frozenset({"hiking", "coffee"}))
    low = make_candidate(id="low", interests=frozenset({"wine"}))
    high = make_candidate(id="high", interests=frozenset({"hiking", "coffee"}))
    repo = FakeRepository(caller=caller, candidates=[low, high])

    results = await FeedService(repository=repo).get_feed(
        caller.id, radius_km=50.0, feed_size=20
    )

    assert [r.id for r in results] == ["high", "low"]
    assert results[0].score == 1.0
    assert results[1].score == 0.0


@pytest.mark.asyncio
async def test_truncates_to_feed_size(make_caller, make_candidate):
    caller = make_caller()
    candidates = [make_candidate(id=str(i)) for i in range(10)]
    repo = FakeRepository(caller=caller, candidates=candidates)

    results = await FeedService(repository=repo).get_feed(
        caller.id, radius_km=50.0, feed_size=3
    )

    assert len(results) == 3


@pytest.mark.asyncio
async def test_passes_candidate_fetch_limit_through_to_repository(
    make_caller, make_candidate
):
    caller = make_caller()
    repo = FakeRepository(caller=caller, candidates=[])

    await FeedService(repository=repo).get_feed(
        caller.id, radius_km=50.0, feed_size=20, candidate_fetch_limit=500
    )

    assert repo.last_limit == 500


@pytest.mark.asyncio
async def test_resolves_photo_url_only_for_returned_candidates(
    make_caller, make_candidate
):
    caller = make_caller()
    with_photo = make_candidate(id="a", photo_key="key-a")
    without_photo = make_candidate(id="b", photo_key=None)
    repo = FakeRepository(caller=caller, candidates=[with_photo, without_photo])
    resolver = FakePhotoResolver({"key-a": "https://cdn.example/a.jpg"})

    results = await FeedService(repository=repo, photo_resolver=resolver).get_feed(
        caller.id, radius_km=50.0, feed_size=20
    )

    by_id = {r.id: r for r in results}
    assert by_id["a"].photo_url == "https://cdn.example/a.jpg"
    assert by_id["b"].photo_url is None


@pytest.mark.asyncio
async def test_no_photo_resolver_leaves_photo_url_none(make_caller, make_candidate):
    caller = make_caller()
    candidate = make_candidate(id="a", photo_key="key-a")
    repo = FakeRepository(caller=caller, candidates=[candidate])

    results = await FeedService(repository=repo).get_feed(
        caller.id, radius_km=50.0, feed_size=20
    )

    assert results[0].photo_url is None


class ConcurrencyTrackingPhotoResolver:
    """Proves photo URLs are resolved concurrently (asyncio.gather), not one
    await at a time — regression guard for ai/audit/lab-5.md's "secondary
    finding". Each resolve() blocks until every candidate's resolve() has
    started; a sequential implementation would deadlock here instead of
    completing, which is exactly the point."""

    def __init__(self, n_expected: int) -> None:
        self._n_expected = n_expected
        self._in_flight = 0
        self._all_started = asyncio.Event()
        self.max_concurrent = 0

    async def resolve(self, photo_key: str) -> str | None:
        self._in_flight += 1
        self.max_concurrent = max(self.max_concurrent, self._in_flight)
        if self._in_flight == self._n_expected:
            self._all_started.set()
        await asyncio.wait_for(self._all_started.wait(), timeout=1.0)
        self._in_flight -= 1
        return f"url-for-{photo_key}"


@pytest.mark.asyncio
async def test_photo_urls_are_resolved_concurrently(make_caller, make_candidate):
    caller = make_caller()
    candidates = [make_candidate(id=str(i), photo_key=f"key-{i}") for i in range(5)]
    repo = FakeRepository(caller=caller, candidates=candidates)
    resolver = ConcurrencyTrackingPhotoResolver(n_expected=5)

    results = await FeedService(repository=repo, photo_resolver=resolver).get_feed(
        caller.id, radius_km=50.0, feed_size=5
    )

    assert resolver.max_concurrent == 5
    assert {r.photo_url for r in results} == {f"url-for-key-{i}" for i in range(5)}
