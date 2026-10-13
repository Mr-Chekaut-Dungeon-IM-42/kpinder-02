import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.chat import service
from app.chat.models import Message
from app.chat.schemas import MessageEditRequest, MessageSendRequest
from app.matching.models import Match


def _make_match(
    user_a_id: uuid.UUID | None = None,
    user_b_id: uuid.UUID | None = None,
) -> Match:
    return Match(
        id=uuid.uuid4(),
        user_a_id=user_a_id or uuid.uuid4(),
        user_b_id=user_b_id or uuid.uuid4(),
        created_at=datetime.now(UTC),
    )


def _make_message(
    match_id: uuid.UUID,
    sender_id: uuid.UUID,
    content: str = "Hello",
    client_message_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> Message:
    return Message(
        id=uuid.uuid4(),
        match_id=match_id,
        sender_id=sender_id,
        client_message_id=client_message_id or uuid.uuid4(),
        content=content,
        created_at=created_at or datetime.now(UTC),
        edited_at=None,
    )


# --- Cursor and Participant Helper Tests ---


def test_cursor_roundtrip():
    now = datetime.now(UTC)
    msg_id = uuid.uuid4()
    cursor = service._encode_cursor(now, msg_id)
    decoded_dt, decoded_id = service._decode_cursor(cursor)
    assert decoded_dt == now
    assert decoded_id == msg_id


@pytest.mark.parametrize(
    "invalid_cursor",
    [
        "not-base64",
        "e30=",  # base64 for "{}" (missing required keys)
        "eyJjcmVhdGVkX2F0IjogImJhZCJ9",  # missing "id"
        "eyJjcmVhdGVkX2F0IjogImJhZCIsICJpZCI6ICIxMjMifQ==",  # bad date
    ],
)
def test_decode_cursor_invalid_raises_422(invalid_cursor: str):
    with pytest.raises(HTTPException) as exc_info:
        service._decode_cursor(invalid_cursor)
    assert exc_info.value.status_code == 422


def test_assert_participant():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    outsider = uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)

    # Caller is user_a -> returns recipient user_b
    assert service._assert_participant(match, user_a) == user_b
    # Caller is user_b -> returns recipient user_a
    assert service._assert_participant(match, user_b) == user_a

    # Caller is outsider -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        service._assert_participant(match, outsider)
    assert exc_info.value.status_code == 403


# --- send_message Tests ---


@pytest.mark.asyncio
async def test_send_message_happy_path():
    db = AsyncMock()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    data = MessageSendRequest(client_message_id=uuid.uuid4(), content="Hi there!")
    created_msg = _make_message(
        match_id=match.id,
        sender_id=user_a,
        content=data.content,
        client_message_id=data.client_message_id,
    )

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch("app.chat.service.repository.create_message", return_value=created_msg),
        patch(
            "app.chat.service.ws_manager.send_event", new_callable=AsyncMock
        ) as mock_ws,
    ):
        result = await service.send_message(db, user_a, match.id, data)

    assert result.content == "Hi there!"
    assert result.sender_id == user_a
    db.commit.assert_awaited_once()
    mock_ws.assert_awaited_once_with(
        user_b, "new_message", result.model_dump(mode="json")
    )


@pytest.mark.asyncio
async def test_send_message_match_not_found():
    db = AsyncMock()
    data = MessageSendRequest(client_message_id=uuid.uuid4(), content="Hi")

    with (
        patch("app.chat.service.repository.get_match", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.send_message(db, uuid.uuid4(), uuid.uuid4(), data)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_send_message_caller_not_participant():
    db = AsyncMock()
    match = _make_match()
    outsider = uuid.uuid4()
    data = MessageSendRequest(client_message_id=uuid.uuid4(), content="Hi")

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.send_message(db, outsider, match.id, data)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_send_message_idempotent_retry_on_duplicate_client_id():
    db = AsyncMock()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    data = MessageSendRequest(client_message_id=uuid.uuid4(), content="Duplicate send")
    existing_msg = _make_message(
        match_id=match.id,
        sender_id=user_a,
        content=data.content,
        client_message_id=data.client_message_id,
    )

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch(
            "app.chat.service.repository.create_message",
            side_effect=IntegrityError("stmt", {}, Exception("unique violation")),
        ),
        patch(
            "app.chat.service.repository.get_message_by_client_id",
            return_value=existing_msg,
        ),
        patch(
            "app.chat.service.ws_manager.send_event", new_callable=AsyncMock
        ) as mock_ws,
    ):
        result = await service.send_message(db, user_a, match.id, data)

    assert result.id == existing_msg.id
    db.rollback.assert_awaited_once()
    mock_ws.assert_not_called()


@pytest.mark.asyncio
async def test_send_message_integrity_error_without_existing_message_reraises():
    db = AsyncMock()
    user_a = uuid.uuid4()
    match = _make_match(user_a_id=user_a)
    data = MessageSendRequest(client_message_id=uuid.uuid4(), content="Fail")

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch(
            "app.chat.service.repository.create_message",
            side_effect=IntegrityError("stmt", {}, Exception("other DB error")),
        ),
        patch(
            "app.chat.service.repository.get_message_by_client_id", return_value=None
        ),
        pytest.raises(IntegrityError),
    ):
        await service.send_message(db, user_a, match.id, data)

    db.rollback.assert_awaited_once()


# --- get_messages Tests ---


@pytest.mark.asyncio
async def test_get_messages_happy_path_fewer_than_limit():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    messages = [_make_message(match.id, user_a, f"Msg {i}") for i in range(5)]

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch(
            "app.chat.service.repository.get_messages_page", return_value=messages
        ) as mock_get_page,
    ):
        page = await service.get_messages(db, user_a, match.id, cursor=None)

    assert len(page.items) == 5
    assert page.next_cursor is None
    # Verifies default limit=20 was passed to repository
    mock_get_page.assert_awaited_once_with(db, match.id, None, None, 20)


@pytest.mark.asyncio
async def test_get_messages_generates_next_cursor_when_limit_reached():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    messages = [
        _make_message(
            match.id,
            user_a,
            f"Msg {i}",
            created_at=base_time + timedelta(seconds=i),
        )
        for i in range(20)
    ]

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch("app.chat.service.repository.get_messages_page", return_value=messages),
    ):
        page = await service.get_messages(db, user_a, match.id, cursor=None)

    assert len(page.items) == 20
    assert page.next_cursor is not None
    dt, msg_id = service._decode_cursor(page.next_cursor)
    assert msg_id == messages[-1].id
    assert dt == messages[-1].created_at


@pytest.mark.asyncio
async def test_get_messages_with_valid_cursor_passes_to_repository():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    last_dt = datetime.now(UTC)
    last_id = uuid.uuid4()
    cursor = service._encode_cursor(last_dt, last_id)

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch(
            "app.chat.service.repository.get_messages_page", return_value=[]
        ) as mock_get_page,
    ):
        page = await service.get_messages(db, user_a, match.id, cursor=cursor, limit=20)

    assert len(page.items) == 0
    mock_get_page.assert_awaited_once_with(db, match.id, last_dt, last_id, 20)


@pytest.mark.asyncio
async def test_get_messages_match_not_found():
    db = AsyncMock()
    with (
        patch("app.chat.service.repository.get_match", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.get_messages(db, uuid.uuid4(), uuid.uuid4(), cursor=None)
    assert exc_info.value.status_code == 404


# --- edit_message Tests ---


@pytest.mark.asyncio
async def test_edit_message_happy_path():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    message = _make_message(match_id=match.id, sender_id=user_a, content="Old content")
    data = MessageEditRequest(content="Updated content")

    def _apply_update(d, msg, c):
        msg.content = c
        msg.edited_at = datetime.now(UTC)
        return msg

    with (
        patch("app.chat.service.repository.get_message_by_id", return_value=message),
        patch("app.chat.service.repository.get_match", return_value=match),
        patch("app.chat.service.repository.update_message", side_effect=_apply_update),
        patch(
            "app.chat.service.ws_manager.send_event", new_callable=AsyncMock
        ) as mock_ws,
    ):
        result = await service.edit_message(db, user_a, message.id, data)

    assert result.content == "Updated content"
    db.commit.assert_awaited_once()
    mock_ws.assert_awaited_once_with(
        user_b, "message_edited", result.model_dump(mode="json")
    )


@pytest.mark.asyncio
async def test_edit_message_not_found():
    db = AsyncMock()
    data = MessageEditRequest(content="Updated")
    with (
        patch("app.chat.service.repository.get_message_by_id", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.edit_message(db, uuid.uuid4(), uuid.uuid4(), data)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_edit_message_forbidden_for_non_sender():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    message = _make_message(match_id=uuid.uuid4(), sender_id=user_a, content="Original")
    data = MessageEditRequest(content="Hacked")

    with (
        patch("app.chat.service.repository.get_message_by_id", return_value=message),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.edit_message(db, user_b, message.id, data)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_edit_message_when_match_is_none():
    db = AsyncMock()
    user_a = uuid.uuid4()
    message = _make_message(match_id=uuid.uuid4(), sender_id=user_a, content="Old")
    data = MessageEditRequest(content="New")

    def _apply_update(d, msg, c):
        msg.content = c
        return msg

    with (
        patch("app.chat.service.repository.get_message_by_id", return_value=message),
        patch("app.chat.service.repository.get_match", return_value=None),
        patch("app.chat.service.repository.update_message", side_effect=_apply_update),
        patch(
            "app.chat.service.ws_manager.send_event", new_callable=AsyncMock
        ) as mock_ws,
    ):
        result = await service.edit_message(db, user_a, message.id, data)

    assert result.content == "New"
    mock_ws.assert_not_called()


# --- delete_message Tests ---


@pytest.mark.asyncio
async def test_delete_message_happy_path():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    message = _make_message(
        match_id=match.id, sender_id=user_a, content="To be deleted"
    )

    with (
        patch("app.chat.service.repository.get_message_by_id", return_value=message),
        patch("app.chat.service.repository.get_match", return_value=match),
        patch("app.chat.service.repository.delete_message") as mock_delete,
        patch(
            "app.chat.service.ws_manager.send_event", new_callable=AsyncMock
        ) as mock_ws,
    ):
        await service.delete_message(db, user_a, message.id)

    mock_delete.assert_awaited_once_with(db, message)
    db.commit.assert_awaited_once()
    mock_ws.assert_awaited_once_with(
        user_b,
        "message_deleted",
        {"id": str(message.id), "match_id": str(match.id)},
    )


@pytest.mark.asyncio
async def test_delete_message_not_found():
    db = AsyncMock()
    with (
        patch("app.chat.service.repository.get_message_by_id", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.delete_message(db, uuid.uuid4(), uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_message_forbidden_for_non_sender():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    message = _make_message(match_id=uuid.uuid4(), sender_id=user_a)

    with (
        patch("app.chat.service.repository.get_message_by_id", return_value=message),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.delete_message(db, user_b, message.id)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_message_when_match_is_none():
    db = AsyncMock()
    user_a = uuid.uuid4()
    message = _make_message(match_id=uuid.uuid4(), sender_id=user_a)

    with (
        patch("app.chat.service.repository.get_message_by_id", return_value=message),
        patch("app.chat.service.repository.get_match", return_value=None),
        patch("app.chat.service.repository.delete_message"),
        patch(
            "app.chat.service.ws_manager.send_event", new_callable=AsyncMock
        ) as mock_ws,
    ):
        await service.delete_message(db, user_a, message.id)

    db.commit.assert_awaited_once()
    mock_ws.assert_not_called()


# --- search_messages Tests ---


@pytest.mark.asyncio
async def test_search_messages_empty_or_whitespace_returns_empty_list():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch("app.chat.service.repository.search_messages") as mock_search,
    ):
        result = await service.search_messages(db, user_a, match.id, "   ")

    assert result == []
    mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_search_messages_happy_path():
    db = AsyncMock()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    match = _make_match(user_a_id=user_a, user_b_id=user_b)
    found_msg = _make_message(match.id, user_b, "Found keyword in message")

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        patch(
            "app.chat.service.repository.search_messages",
            return_value=[found_msg],
        ) as mock_search,
    ):
        results = await service.search_messages(db, user_a, match.id, " keyword ")

    assert len(results) == 1
    assert results[0].id == found_msg.id
    mock_search.assert_awaited_once_with(db, match.id, "keyword")


@pytest.mark.asyncio
async def test_search_messages_match_not_found():
    db = AsyncMock()
    with (
        patch("app.chat.service.repository.get_match", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.search_messages(db, uuid.uuid4(), uuid.uuid4(), "query")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_search_messages_caller_not_participant():
    db = AsyncMock()
    match = _make_match()
    outsider = uuid.uuid4()

    with (
        patch("app.chat.service.repository.get_match", return_value=match),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service.search_messages(db, outsider, match.id, "query")
    assert exc_info.value.status_code == 403
