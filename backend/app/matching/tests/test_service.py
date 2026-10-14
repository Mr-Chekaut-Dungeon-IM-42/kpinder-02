import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.matching import service
from app.matching.models import Match, Swipe
from app.matching.schemas import SwipeRequest
from app.shared.models import Interest, User, UserInterest


def test_jaccard_both_empty_scores_zero():
    assert service._jaccard(set(), set()) == 0.0


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
async def test_get_feed_unknown_caller_raises_404():
    db = AsyncMock()
    with (
        patch(
            "app.matching.service.repository.get_user_with_interests",
            return_value=None,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.get_feed(db, uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_feed_resolves_photo_url_for_candidate_with_photo():
    db = AsyncMock()
    caller = _with_interests(_user(location="POINT"), "hiking")
    candidate = _with_interests(_user(photo_key="some-key.jpg"), "hiking")

    with (
        patch(
            "app.matching.service.repository.get_user_with_interests",
            return_value=caller,
        ),
        patch(
            "app.matching.service.repository.get_candidates",
            return_value=[candidate],
        ),
        patch("app.matching.service.get_photo_storage", return_value="storage"),
        patch(
            "app.matching.service.resolve_photo_url",
            return_value="https://example.com/photo.jpg",
        ) as resolve_mock,
    ):
        result = await service.get_feed(db, caller.id)

    assert result[0].photo_url == "https://example.com/photo.jpg"
    resolve_mock.assert_awaited_once_with("storage", "some-key.jpg")


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


@pytest.mark.asyncio
async def test_swipe_match_insert_race_loses_but_match_exists():
    """Both sides' swipes land, both see the reciprocal like, and both try to
    insert the Match row — this one loses the unique-constraint race but the
    winner's row is already there (ADR-0009)."""
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    reciprocal = Swipe(swiper_id=target_id, swiped_id=caller_id, decision="like")
    match = Match(id=uuid.uuid4(), user_a_id=caller_id, user_b_id=target_id)

    with (
        patch("app.matching.service.repository.user_exists", return_value=True),
        patch("app.matching.service.repository.create_swipe"),
        patch("app.matching.service.repository.get_swipe", return_value=reciprocal),
        patch(
            "app.matching.service.repository.create_match",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.service.repository.get_match_between", return_value=match),
    ):
        result = await service.swipe(db, caller_id, data)

    assert result.matched is True
    assert result.match_id == match.id
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_swipe_match_insert_race_loses_and_match_not_found_yet():
    """Pathological race edge: create_match hits the unique violation, but a
    concurrent lookup doesn't see the winner's row yet — matched stays True
    (the business fact is still "they matched") with no match_id to show."""
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    reciprocal = Swipe(swiper_id=target_id, swiped_id=caller_id, decision="like")

    with (
        patch("app.matching.service.repository.user_exists", return_value=True),
        patch("app.matching.service.repository.create_swipe"),
        patch("app.matching.service.repository.get_swipe", return_value=reciprocal),
        patch(
            "app.matching.service.repository.create_match",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.service.repository.get_match_between", return_value=None),
    ):
        result = await service.swipe(db, caller_id, data)

    assert result.matched is True
    assert result.match_id is None


def test_cursor_round_trip():
    match_id = uuid.uuid4()
    created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    cursor = service._encode_cursor(created_at, match_id)
    decoded_at, decoded_id = service._decode_cursor(cursor)
    assert decoded_at == created_at
    assert decoded_id == match_id


def test_decode_cursor_invalid_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        service._decode_cursor("not-a-valid-cursor")
    assert exc_info.value.status_code == 422


def _match(**kwargs) -> Match:
    defaults = dict(
        id=uuid.uuid4(),
        user_a_id=uuid.uuid4(),
        user_b_id=uuid.uuid4(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(kwargs)
    return Match(**defaults)


@pytest.mark.asyncio
async def test_get_matches_empty_page():
    db = AsyncMock()
    with (
        patch("app.matching.service.repository.get_matches_page", return_value=[]),
        patch("app.matching.service.repository.get_users_by_ids", return_value={}),
    ):
        page = await service.get_matches(db, uuid.uuid4(), cursor=None)

    assert page.items == []
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_get_matches_resolves_other_user_when_caller_is_user_a():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user()
    match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch("app.matching.service.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.service.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        page = await service.get_matches(db, caller_id, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].other_user.id == other.id


@pytest.mark.asyncio
async def test_get_matches_resolves_other_user_when_caller_is_user_b():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user()
    match = _match(user_a_id=other.id, user_b_id=caller_id)

    with (
        patch("app.matching.service.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.service.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        page = await service.get_matches(db, caller_id, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].other_user.id == other.id


@pytest.mark.asyncio
async def test_get_matches_skips_match_when_other_user_missing():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    match = _match(user_a_id=caller_id, user_b_id=uuid.uuid4())

    with (
        patch("app.matching.service.repository.get_matches_page", return_value=[match]),
        patch("app.matching.service.repository.get_users_by_ids", return_value={}),
    ):
        page = await service.get_matches(db, caller_id, cursor=None)

    assert page.items == []


@pytest.mark.asyncio
async def test_get_matches_resolves_photo_url_when_other_has_photo():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user(photo_key="some-key.jpg")
    match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch("app.matching.service.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.service.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
        patch("app.matching.service.get_photo_storage", return_value="storage"),
        patch(
            "app.matching.service.resolve_photo_url",
            return_value="https://example.com/photo.jpg",
        ) as resolve_mock,
    ):
        page = await service.get_matches(db, caller_id, cursor=None)

    assert page.items[0].other_user.photo_url == "https://example.com/photo.jpg"
    resolve_mock.assert_awaited_once_with("storage", "some-key.jpg")


@pytest.mark.asyncio
async def test_get_matches_sets_next_cursor_when_page_is_full():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user()
    match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch("app.matching.service.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.service.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        page = await service.get_matches(db, caller_id, cursor=None, limit=1)

    assert page.next_cursor is not None
    decoded_at, decoded_id = service._decode_cursor(page.next_cursor)
    assert decoded_id == match.id


@pytest.mark.asyncio
async def test_get_matches_no_next_cursor_when_page_not_full():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user()
    match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch("app.matching.service.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.service.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        page = await service.get_matches(db, caller_id, cursor=None, limit=20)

    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_get_matches_passes_decoded_cursor_to_repository():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    match_id = uuid.uuid4()
    cursor = service._encode_cursor(created_at, match_id)

    with (
        patch(
            "app.matching.service.repository.get_matches_page", return_value=[]
        ) as get_page_mock,
        patch("app.matching.service.repository.get_users_by_ids", return_value={}),
    ):
        await service.get_matches(db, caller_id, cursor=cursor, limit=20)

    get_page_mock.assert_awaited_once_with(db, caller_id, created_at, match_id, 20)
