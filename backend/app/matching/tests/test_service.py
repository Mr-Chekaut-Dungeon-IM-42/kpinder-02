import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.matching import service
from app.matching.models import Match, Swipe
from app.matching.schemas import SwipeRequest
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
async def test_get_feed_requires_location():
    db = AsyncMock()
    caller = _user(location=None)
    with (
        patch(
            "app.matching.service.repository.get_user_with_interests",
            return_value=caller,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.get_feed(db, caller.id)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_get_feed_sorts_by_interest_overlap():
    db = AsyncMock()
    caller = _with_interests(_user(location="POINT"), "hiking", "coffee")
    low = _with_interests(_user(), "wine")
    high = _with_interests(_user(), "hiking", "coffee")

    with (
        patch(
            "app.matching.service.repository.get_user_with_interests",
            return_value=caller,
        ),
        patch(
            "app.matching.service.repository.get_candidates",
            return_value=[low, high],
        ),
    ):
        result = await service.get_feed(db, caller.id)

    assert [c.id for c in result] == [high.id, low.id]


@pytest.mark.asyncio
async def test_swipe_pass_never_matches():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="pass")

    with (
        patch("app.matching.service.repository.user_exists", return_value=True),
        patch("app.matching.service.repository.create_swipe"),
    ):
        result = await service.swipe(db, caller_id, data)

    assert result.matched is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_swipe_like_with_no_reciprocal_does_not_match():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")

    with (
        patch("app.matching.service.repository.user_exists", return_value=True),
        patch("app.matching.service.repository.create_swipe"),
        patch("app.matching.service.repository.get_swipe", return_value=None),
    ):
        result = await service.swipe(db, caller_id, data)

    assert result.matched is False


@pytest.mark.asyncio
async def test_swipe_like_with_reciprocal_creates_match():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    reciprocal = Swipe(swiper_id=target_id, swiped_id=caller_id, decision="like")
    match = Match(id=uuid.uuid4(), user_a_id=caller_id, user_b_id=target_id)

    with (
        patch("app.matching.service.repository.user_exists", return_value=True),
        patch("app.matching.service.repository.create_swipe"),
        patch("app.matching.service.repository.get_swipe", return_value=reciprocal),
        patch("app.matching.service.repository.create_match", return_value=match),
    ):
        result = await service.swipe(db, caller_id, data)

    assert result.matched is True
    assert result.match_id == match.id


@pytest.mark.asyncio
async def test_swipe_idempotent_same_decision_retry():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    existing = Swipe(swiper_id=caller_id, swiped_id=target_id, decision="like")
    match = Match(id=uuid.uuid4(), user_a_id=caller_id, user_b_id=target_id)

    with (
        patch("app.matching.service.repository.user_exists", return_value=True),
        patch(
            "app.matching.service.repository.create_swipe",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.service.repository.get_swipe", return_value=existing),
        patch("app.matching.service.repository.get_match_between", return_value=match),
    ):
        result = await service.swipe(db, caller_id, data)

    assert result.matched is True
    assert result.match_id == match.id
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_swipe_different_decision_raises_409():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    existing = Swipe(swiper_id=caller_id, swiped_id=target_id, decision="pass")

    with (
        patch("app.matching.service.repository.user_exists", return_value=True),
        patch(
            "app.matching.service.repository.create_swipe",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.service.repository.get_swipe", return_value=existing),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.swipe(db, caller_id, data)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_swipe_unknown_target_raises_404():
    db = AsyncMock()
    data = SwipeRequest(target_id=uuid.uuid4(), decision="like")
    with (
        patch("app.matching.service.repository.user_exists", return_value=False),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.swipe(db, uuid.uuid4(), data)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_swipe_on_self_raises_422():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    data = SwipeRequest(target_id=caller_id, decision="like")
    with pytest.raises(HTTPException) as exc_info:
        await service.swipe(db, caller_id, data)
    assert exc_info.value.status_code == 422
