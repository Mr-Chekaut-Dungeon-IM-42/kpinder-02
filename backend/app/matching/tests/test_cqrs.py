import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.matching.commands import SwipeCommand
from app.matching.common import decode_cursor, encode_cursor
from app.matching.queries import GetMatchesQuery
from app.matching.schemas import SwipeRequest
from app.shared.models import Match, Swipe, User


def _user(**kwargs) -> User:
    defaults = dict(id=uuid.uuid4(), email="a@b.com", password_hash="x", name="Alice")
    defaults.update(kwargs)
    user = User(**defaults)
    user.interests = []
    return user


# GetFeedQuery's own ranking/selection logic is tested against
# matching_core's FeedService directly (libs/matching-core/tests/
# test_feed.py, with in-memory fakes — no SQLAlchemy mocking needed).
# app/matching/tests/test_feed_adapter.py covers the thin adapter glue
# (error translation, schema mapping) that lives in this app instead.


# --- SwipeCommand Tests ---


@pytest.mark.asyncio
async def test_swipe_pass_never_matches():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="pass")

    with (
        patch("app.matching.commands.repository.user_exists", return_value=True),
        patch("app.matching.commands.repository.create_swipe"),
    ):
        cmd = SwipeCommand(db=db)
        result = await cmd.execute(caller_id, data)

    assert result.matched is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_swipe_like_with_no_reciprocal_does_not_match():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")

    with (
        patch("app.matching.commands.repository.user_exists", return_value=True),
        patch("app.matching.commands.repository.create_swipe"),
        patch("app.matching.commands.repository.get_swipe", return_value=None),
    ):
        cmd = SwipeCommand(db=db)
        result = await cmd.execute(caller_id, data)

    assert result.matched is False


@pytest.mark.asyncio
async def test_swipe_like_with_reciprocal_creates_match():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    reciprocal = Swipe(swiper_id=target_id, swiped_id=caller_id, decision="like")
    match = Match(id=uuid.uuid4(), user_a_id=caller_id, user_b_id=target_id)

    with (
        patch("app.matching.commands.repository.user_exists", return_value=True),
        patch("app.matching.commands.repository.create_swipe"),
        patch("app.matching.commands.repository.get_swipe", return_value=reciprocal),
        patch("app.matching.commands.repository.create_match", return_value=match),
    ):
        cmd = SwipeCommand(db=db)
        result = await cmd.execute(caller_id, data)

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
        patch("app.matching.commands.repository.user_exists", return_value=True),
        patch(
            "app.matching.commands.repository.create_swipe",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.commands.repository.get_swipe", return_value=existing),
        patch("app.matching.commands.repository.get_match_between", return_value=match),
    ):
        cmd = SwipeCommand(db=db)
        result = await cmd.execute(caller_id, data)

    assert result.matched is True
    assert result.match_id == match.id
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_swipe_idempotent_pass_retry_has_no_match():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="pass")
    existing = Swipe(swiper_id=caller_id, swiped_id=target_id, decision="pass")

    with (
        patch("app.matching.commands.repository.user_exists", return_value=True),
        patch(
            "app.matching.commands.repository.create_swipe",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.commands.repository.get_swipe", return_value=existing),
        patch("app.matching.commands.repository.get_match_between", return_value=None),
    ):
        cmd = SwipeCommand(db=db)
        result = await cmd.execute(caller_id, data)

    assert result.matched is False
    assert result.match_id is None


@pytest.mark.asyncio
async def test_swipe_different_decision_raises_409():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    existing = Swipe(swiper_id=caller_id, swiped_id=target_id, decision="pass")

    with (
        patch("app.matching.commands.repository.user_exists", return_value=True),
        patch(
            "app.matching.commands.repository.create_swipe",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.commands.repository.get_swipe", return_value=existing),
        pytest.raises(HTTPException) as exc_info,
    ):
        cmd = SwipeCommand(db=db)
        await cmd.execute(caller_id, data)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_swipe_unknown_target_raises_404():
    db = AsyncMock()
    data = SwipeRequest(target_id=uuid.uuid4(), decision="like")
    with (
        patch("app.matching.commands.repository.user_exists", return_value=False),
        pytest.raises(HTTPException) as exc_info,
    ):
        cmd = SwipeCommand(db=db)
        await cmd.execute(uuid.uuid4(), data)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_swipe_on_self_raises_422():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    data = SwipeRequest(target_id=caller_id, decision="like")
    with pytest.raises(HTTPException) as exc_info:
        cmd = SwipeCommand(db=db)
        await cmd.execute(caller_id, data)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_swipe_match_insert_race_loses_but_match_exists():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    reciprocal = Swipe(swiper_id=target_id, swiped_id=caller_id, decision="like")
    match = Match(id=uuid.uuid4(), user_a_id=caller_id, user_b_id=target_id)

    with (
        patch("app.matching.commands.repository.user_exists", return_value=True),
        patch("app.matching.commands.repository.create_swipe"),
        patch("app.matching.commands.repository.get_swipe", return_value=reciprocal),
        patch(
            "app.matching.commands.repository.create_match",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.commands.repository.get_match_between", return_value=match),
    ):
        cmd = SwipeCommand(db=db)
        result = await cmd.execute(caller_id, data)

    assert result.matched is True
    assert result.match_id == match.id
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_swipe_match_insert_race_loses_and_match_not_found_yet():
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="like")
    reciprocal = Swipe(swiper_id=target_id, swiped_id=caller_id, decision="like")

    with (
        patch("app.matching.commands.repository.user_exists", return_value=True),
        patch("app.matching.commands.repository.create_swipe"),
        patch("app.matching.commands.repository.get_swipe", return_value=reciprocal),
        patch(
            "app.matching.commands.repository.create_match",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.commands.repository.get_match_between", return_value=None),
    ):
        cmd = SwipeCommand(db=db)
        result = await cmd.execute(caller_id, data)

    assert result.matched is True
    assert result.match_id is None


# --- Cursor Helper Tests ---


def test_cursor_round_trip():
    match_id = uuid.uuid4()
    created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    cursor = encode_cursor(created_at, match_id)
    decoded_at, decoded_id = decode_cursor(cursor)
    assert decoded_at == created_at
    assert decoded_id == match_id


def test_decode_cursor_invalid_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        decode_cursor("not-a-valid-cursor")
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


# --- GetMatchesQuery Tests ---


@pytest.mark.asyncio
async def test_get_matches_empty_page():
    db = AsyncMock()
    with (
        patch("app.matching.queries.repository.get_matches_page", return_value=[]),
        patch("app.matching.queries.repository.get_users_by_ids", return_value={}),
    ):
        query = GetMatchesQuery(db=db)
        page = await query.execute(uuid.uuid4(), cursor=None)

    assert page.items == []
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_get_matches_resolves_other_user_when_caller_is_user_a():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user()
    match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch("app.matching.queries.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.queries.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        query = GetMatchesQuery(db=db)
        page = await query.execute(caller_id, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].other_user.id == other.id


@pytest.mark.asyncio
async def test_get_matches_resolves_other_user_when_caller_is_user_b():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user()
    match = _match(user_a_id=other.id, user_b_id=caller_id)

    with (
        patch("app.matching.queries.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.queries.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        query = GetMatchesQuery(db=db)
        page = await query.execute(caller_id, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].other_user.id == other.id


@pytest.mark.asyncio
async def test_get_matches_skips_match_when_other_user_missing():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    match = _match(user_a_id=caller_id, user_b_id=uuid.uuid4())

    with (
        patch("app.matching.queries.repository.get_matches_page", return_value=[match]),
        patch("app.matching.queries.repository.get_users_by_ids", return_value={}),
    ):
        query = GetMatchesQuery(db=db)
        page = await query.execute(caller_id, cursor=None)

    assert page.items == []


@pytest.mark.asyncio
async def test_get_matches_continues_past_missing_user_to_later_matches():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    missing_match = _match(user_a_id=caller_id, user_b_id=uuid.uuid4())
    other = _user()
    present_match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch(
            "app.matching.queries.repository.get_matches_page",
            return_value=[missing_match, present_match],
        ),
        patch(
            "app.matching.queries.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        query = GetMatchesQuery(db=db)
        page = await query.execute(caller_id, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].other_user.id == other.id


@pytest.mark.asyncio
async def test_get_matches_resolves_photo_url_when_other_has_photo():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user(photo_key="some-key.jpg")
    match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch("app.matching.queries.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.queries.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
        patch("app.matching.queries.get_photo_storage", return_value="storage"),
        patch(
            "app.matching.queries.resolve_photo_url",
            return_value="https://example.com/photo.jpg",
        ) as resolve_mock,
    ):
        query = GetMatchesQuery(db=db)
        page = await query.execute(caller_id, cursor=None)

    assert page.items[0].other_user.photo_url == "https://example.com/photo.jpg"
    resolve_mock.assert_awaited_once_with("storage", "some-key.jpg")


@pytest.mark.asyncio
async def test_get_matches_sets_next_cursor_when_page_is_full():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user()
    match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch("app.matching.queries.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.queries.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        query = GetMatchesQuery(db=db)
        page = await query.execute(caller_id, cursor=None, limit=1)

    assert page.next_cursor is not None
    decoded_at, decoded_id = decode_cursor(page.next_cursor)
    assert decoded_id == match.id


@pytest.mark.asyncio
async def test_get_matches_no_next_cursor_when_page_not_full():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    other = _user()
    match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch("app.matching.queries.repository.get_matches_page", return_value=[match]),
        patch(
            "app.matching.queries.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        query = GetMatchesQuery(db=db)
        page = await query.execute(caller_id, cursor=None, limit=20)

    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_get_matches_uses_default_limit_of_twenty():
    db = AsyncMock()
    caller_id = uuid.uuid4()

    with (
        patch(
            "app.matching.queries.repository.get_matches_page", return_value=[]
        ) as get_page_mock,
        patch("app.matching.queries.repository.get_users_by_ids", return_value={}),
    ):
        query = GetMatchesQuery(db=db)
        await query.execute(caller_id, cursor=None)

    get_page_mock.assert_awaited_once_with(db, caller_id, None, None, 20)


@pytest.mark.asyncio
async def test_get_matches_passes_decoded_cursor_to_repository():
    db = AsyncMock()
    caller_id = uuid.uuid4()
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    match_id = uuid.uuid4()
    cursor = encode_cursor(created_at, match_id)

    with (
        patch(
            "app.matching.queries.repository.get_matches_page", return_value=[]
        ) as get_page_mock,
        patch("app.matching.queries.repository.get_users_by_ids", return_value={}),
    ):
        query = GetMatchesQuery(db=db)
        await query.execute(caller_id, cursor=cursor, limit=20)

    get_page_mock.assert_awaited_once_with(db, caller_id, created_at, match_id, 20)
