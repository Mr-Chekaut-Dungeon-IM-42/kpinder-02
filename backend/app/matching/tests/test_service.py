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
    candidate = _with_interests(
        _user(photo_key="some-key.jpg", age=29, bio="Hello"), "hiking"
    )

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
    # age/bio were being set but never asserted anywhere in the feed tests —
    # a mutant that dropped either to None on CandidateResponse survived
    # undetected.
    assert result[0].age == 29
    assert result[0].bio == "Hello"
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
async def test_get_feed_ranks_by_jaccard_ratio_not_raw_intersection_size():
    """A candidate with a smaller raw overlap but a much smaller interest set
    (a tighter *ratio*) must outrank one with a larger overlap buried in a
    big, mostly-unrelated interest set. `len(a & b) / len(a | b)` and
    `len(a & b) * len(a | b)` agree on every two-candidate case the previous
    test used, so a mutant swapping division for multiplication survived —
    this data specifically makes the two formulas disagree on ranking order."""
    db = AsyncMock()
    caller = _with_interests(_user(location="POINT"), "a", "b", "c")
    # tight_fit: overlap=2, union=3 -> jaccard 0.667, product 6
    tight_fit = _with_interests(_user(), "a", "b")
    # broad_overlap: overlap=3, union=10 -> jaccard 0.3, product 30
    broad_overlap = _with_interests(
        _user(), "a", "b", "c", "d", "e", "f", "g", "h", "i", "j"
    )

    with (
        patch(
            "app.matching.service.repository.get_user_with_interests",
            return_value=caller,
        ),
        patch(
            "app.matching.service.repository.get_candidates",
            return_value=[broad_overlap, tight_fit],
        ),
    ):
        result = await service.get_feed(db, caller.id)

    assert [c.id for c in result] == [tight_fit.id, broad_overlap.id]


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
async def test_swipe_idempotent_pass_retry_has_no_match():
    """A 'pass' can never produce a match, so an idempotent pass-retry must
    resolve matched=False/match_id=None via `get_match_between` returning
    None — without this, `match.id if match else None` was never exercised
    with match=None, so a mutant that forces that ternary always-truthy
    (`if (match) or True`) survived undetected; with match=None it would
    crash on `None.id` instead of returning None."""
    db = AsyncMock()
    caller_id, target_id = uuid.uuid4(), uuid.uuid4()
    data = SwipeRequest(target_id=target_id, decision="pass")
    existing = Swipe(swiper_id=caller_id, swiped_id=target_id, decision="pass")

    with (
        patch("app.matching.service.repository.user_exists", return_value=True),
        patch(
            "app.matching.service.repository.create_swipe",
            side_effect=IntegrityError("stmt", {}, Exception("dup")),
        ),
        patch("app.matching.service.repository.get_swipe", return_value=existing),
        patch("app.matching.service.repository.get_match_between", return_value=None),
    ):
        result = await service.swipe(db, caller_id, data)

    assert result.matched is False
    assert result.match_id is None


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
async def test_get_matches_continues_past_missing_user_to_later_matches():
    """A missing 'other' user must only skip *that one* match, not abort the
    page — `continue` is required here, not `break`. With only one match in
    the page (as in the sibling test above), both statements leave an empty
    `page.items`, so a mutant that swapped `continue` for `break` survived:
    this test puts a valid match *after* the missing one so the two diverge
    — `break` would silently drop every match that follows a single missing
    user, truncating the whole page instead of skipping one row."""
    db = AsyncMock()
    caller_id = uuid.uuid4()
    missing_match = _match(user_a_id=caller_id, user_b_id=uuid.uuid4())
    other = _user()
    present_match = _match(user_a_id=caller_id, user_b_id=other.id)

    with (
        patch(
            "app.matching.service.repository.get_matches_page",
            return_value=[missing_match, present_match],
        ),
        patch(
            "app.matching.service.repository.get_users_by_ids",
            return_value={other.id: other},
        ),
    ):
        page = await service.get_matches(db, caller_id, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].other_user.id == other.id


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
async def test_get_matches_uses_default_limit_of_twenty():
    """Every other get_matches test passes limit=20 explicitly, so the
    default-parameter contract (`limit: int = 20`) itself was never
    exercised — a mutant changing the default to 21 survived undetected.
    This test omits `limit` so execution depends entirely on the default."""
    db = AsyncMock()
    caller_id = uuid.uuid4()

    with (
        patch(
            "app.matching.service.repository.get_matches_page", return_value=[]
        ) as get_page_mock,
        patch("app.matching.service.repository.get_users_by_ids", return_value={}),
    ):
        await service.get_matches(db, caller_id, cursor=None)

    get_page_mock.assert_awaited_once_with(db, caller_id, None, None, 20)


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
