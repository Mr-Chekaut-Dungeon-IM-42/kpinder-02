import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.auth import service
from app.auth.schemas import ProfileUpdateRequest
from app.shared.models import Interest, User


def _user(**kwargs) -> User:
    defaults = dict(id=uuid.uuid4(), email="a@b.com", password_hash="x", name="Alice")
    defaults.update(kwargs)
    user = User(**defaults)
    user.interests = []
    return user


def test_age_min_greater_than_age_max_rejected_by_schema():
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(age_min=40, age_max=20, interests=[])


@pytest.mark.asyncio
async def test_update_profile_success():
    db = AsyncMock()
    user = _user()
    interest = Interest(id=uuid.uuid4(), name="hiking")
    data = ProfileUpdateRequest(bio="hi", age=28, interests=["hiking"])

    with (
        patch("app.auth.service.repository.get_user_by_id", return_value=user),
        patch(
            "app.auth.service.repository.get_interests_by_names",
            return_value=[interest],
        ),
        patch("app.auth.service.repository.replace_user_interests") as replace,
    ):
        result = await service.update_profile(db, user.id, data)

    assert result.bio == "hi"
    assert result.age == 28
    replace.assert_awaited_once_with(db, user, [interest])
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_profile_unknown_interest_raises_422():
    db = AsyncMock()
    user = _user()
    data = ProfileUpdateRequest(interests=["not-real"])

    with (
        patch("app.auth.service.repository.get_user_by_id", return_value=user),
        patch("app.auth.service.repository.get_interests_by_names", return_value=[]),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.update_profile(db, user.id, data)

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_get_profile_missing_user_raises_404():
    db = AsyncMock()
    with (
        patch("app.auth.service.repository.get_user_by_id", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.get_profile(db, uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_interests_returns_repository_result():
    db = AsyncMock()
    interests = [Interest(id=uuid.uuid4(), name="hiking")]
    with patch(
        "app.auth.service.repository.list_interests", return_value=interests
    ) as list_mock:
        result = await service.list_interests(db)

    list_mock.assert_awaited_once_with(db)
    assert result == interests


@pytest.mark.asyncio
async def test_update_profile_sets_location_when_lat_lng_provided():
    db = AsyncMock()
    user = _user()
    data = ProfileUpdateRequest(
        latitude=50.45, longitude=30.52, location_label="Kyiv, Ukraine", interests=[]
    )

    with (
        patch("app.auth.service.repository.get_user_by_id", return_value=user),
        patch("app.auth.service.repository.get_interests_by_names", return_value=[]),
        patch("app.auth.service.repository.replace_user_interests"),
    ):
        result = await service.update_profile(db, user.id, data)

    assert result.location_label == "Kyiv, Ukraine"
    assert result.location is not None
    assert "30.52" in str(result.location.data)
    assert "50.45" in str(result.location.data)


@pytest.mark.asyncio
async def test_update_profile_leaves_location_untouched_without_lat_lng():
    db = AsyncMock()
    user = _user(location="existing-point", location_label="Existing")
    data = ProfileUpdateRequest(interests=[])

    with (
        patch("app.auth.service.repository.get_user_by_id", return_value=user),
        patch("app.auth.service.repository.get_interests_by_names", return_value=[]),
        patch("app.auth.service.repository.replace_user_interests"),
    ):
        result = await service.update_profile(db, user.id, data)

    assert result.location == "existing-point"
    assert result.location_label == "Existing"
