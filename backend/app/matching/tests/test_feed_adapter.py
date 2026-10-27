import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.matching.queries import GetFeedQuery
from app.shared.models import Interest, User, UserInterest


def _user(**kwargs) -> User:
    defaults = dict(id=uuid.uuid4(), email="a@b.com", password_hash="x", name="Alice")
    defaults.update(kwargs)
    user = User(**defaults)
    user.interests = []
    return user


def _with_interests(user: User, *names: str) -> User:
    user.interests = [
        UserInterest(interest=Interest(id=uuid.uuid4(), name=name)) for name in names
    ]
    return user


@pytest.mark.asyncio
async def test_unknown_caller_translates_to_404():
    db = AsyncMock()
    with (
        patch(
            "app.matching.adapters.repository.get_user_with_interests",
            return_value=None,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await GetFeedQuery(db=db).execute(uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_caller_without_location_translates_to_422():
    db = AsyncMock()
    caller = _user(location=None)
    with (
        patch(
            "app.matching.adapters.repository.get_user_with_interests",
            return_value=caller,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await GetFeedQuery(db=db).execute(caller.id)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_resolves_photo_url_and_maps_to_candidate_response():
    db = AsyncMock()
    caller = _with_interests(_user(location="POINT"), "hiking")
    candidate = _with_interests(
        _user(photo_key="some-key.jpg", age=29, bio="Hello"), "hiking"
    )

    with (
        patch(
            "app.matching.adapters.repository.get_user_with_interests",
            return_value=caller,
        ),
        patch(
            "app.matching.adapters.repository.get_candidates",
            return_value=[candidate],
        ),
        patch("app.matching.adapters.get_photo_storage", return_value="storage"),
        patch(
            "app.matching.adapters.resolve_photo_url",
            return_value="https://example.com/photo.jpg",
        ) as resolve_mock,
    ):
        result = await GetFeedQuery(db=db).execute(caller.id)

    assert result[0].photo_url == "https://example.com/photo.jpg"
    assert result[0].age == 29
    assert result[0].bio == "Hello"
    assert result[0].id == candidate.id
    resolve_mock.assert_awaited_once_with("storage", "some-key.jpg")


@pytest.mark.asyncio
async def test_sorts_by_interest_overlap_end_to_end():
    db = AsyncMock()
    caller = _with_interests(_user(location="POINT"), "hiking", "coffee")
    low = _with_interests(_user(), "wine")
    high = _with_interests(_user(), "hiking", "coffee")

    with (
        patch(
            "app.matching.adapters.repository.get_user_with_interests",
            return_value=caller,
        ),
        patch(
            "app.matching.adapters.repository.get_candidates",
            return_value=[low, high],
        ),
    ):
        result = await GetFeedQuery(db=db).execute(caller.id)

    assert [c.id for c in result] == [high.id, low.id]
