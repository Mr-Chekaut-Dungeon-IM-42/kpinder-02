import pytest

from matching_core.models import CallerProfile, CandidateProfile


@pytest.fixture
def make_caller():
    def _make(
        id: str = "caller-1",
        gender: str | None = "female",
        seeking: str | None = "male",
        age_min: int | None = None,
        age_max: int | None = None,
        has_location: bool = True,
        interests: frozenset[str] = frozenset(),
    ) -> CallerProfile:
        return CallerProfile(
            id=id,
            gender=gender,
            seeking=seeking,
            age_min=age_min,
            age_max=age_max,
            has_location=has_location,
            interests=interests,
        )

    return _make


@pytest.fixture
def make_candidate():
    def _make(
        id: str = "candidate-1",
        name: str = "Alex",
        age: int | None = 25,
        bio: str | None = None,
        photo_key: str | None = None,
        interests: frozenset[str] = frozenset(),
    ) -> CandidateProfile:
        return CandidateProfile(
            id=id, name=name, age=age, bio=bio, photo_key=photo_key, interests=interests
        )

    return _make
