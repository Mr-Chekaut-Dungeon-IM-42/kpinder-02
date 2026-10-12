import base64
import json
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import repository
from app.chat.schemas import (
    MessageEditRequest,
    MessageResponse,
    MessageSendRequest,
    MessagesPage,
)
from app.matching.models import Match
from app.shared.ws import ws_manager


def _encode_cursor(created_at: datetime, message_id: uuid.UUID) -> str:
    payload = json.dumps({"created_at": created_at.isoformat(), "id": str(message_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["created_at"]), uuid.UUID(payload["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid cursor"
        ) from exc


def _assert_participant(match: Match, caller_id: uuid.UUID) -> uuid.UUID:
    if match.user_a_id != caller_id and match.user_b_id != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a participant in this conversation",
        )
    return match.user_b_id if match.user_a_id == caller_id else match.user_a_id


async def send_message(
    db: AsyncSession,
    caller_id: uuid.UUID,
    match_id: uuid.UUID,
    data: MessageSendRequest,
) -> MessageResponse:
    match = await repository.get_match(db, match_id)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
        )

    recipient_id = _assert_participant(match, caller_id)

    try:
        message = await repository.create_message(
            db, match_id, caller_id, data.client_message_id, data.content
        )
        await db.commit()
        is_new = True
    except IntegrityError:
        await db.rollback()
        existing = await repository.get_message_by_client_id(
            db, match_id, caller_id, data.client_message_id
        )
        if existing is None:
            raise
        message = existing
        is_new = False

    response = MessageResponse.model_validate(message)
    if is_new:
        await ws_manager.send_event(
            recipient_id, "new_message", response.model_dump(mode="json")
        )

    return response


async def get_messages(
    db: AsyncSession,
    caller_id: uuid.UUID,
    match_id: uuid.UUID,
    cursor: str | None,
    limit: int = 20,
) -> MessagesPage:
    match = await repository.get_match(db, match_id)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
        )

    _assert_participant(match, caller_id)

    cursor_created_at, cursor_id = (None, None)
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_cursor(cursor)

    messages = await repository.get_messages_page(
        db, match_id, cursor_created_at, cursor_id, limit
    )

    next_cursor = None
    if len(messages) == limit:
        next_cursor = _encode_cursor(messages[-1].created_at, messages[-1].id)

    return MessagesPage(
        items=[MessageResponse.model_validate(m) for m in messages],
        next_cursor=next_cursor,
    )


async def edit_message(
    db: AsyncSession,
    caller_id: uuid.UUID,
    message_id: uuid.UUID,
    data: MessageEditRequest,
) -> MessageResponse:
    message = await repository.get_message_by_id(db, message_id)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )

    if message.sender_id != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit another user's message",
        )

    match = await repository.get_match(db, message.match_id)
    recipient_id = _assert_participant(match, caller_id) if match else None

    updated = await repository.update_message(db, message, data.content)
    await db.commit()

    response = MessageResponse.model_validate(updated)
    if recipient_id:
        await ws_manager.send_event(
            recipient_id, "message_edited", response.model_dump(mode="json")
        )

    return response


async def delete_message(
    db: AsyncSession, caller_id: uuid.UUID, message_id: uuid.UUID
) -> None:
    message = await repository.get_message_by_id(db, message_id)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )

    if message.sender_id != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete another user's message",
        )

    match_id = message.match_id
    match = await repository.get_match(db, match_id)
    recipient_id = _assert_participant(match, caller_id) if match else None

    await repository.delete_message(db, message)
    await db.commit()

    if recipient_id:
        await ws_manager.send_event(
            recipient_id,
            "message_deleted",
            {"id": str(message_id), "match_id": str(match_id)},
        )


async def search_messages(
    db: AsyncSession, caller_id: uuid.UUID, match_id: uuid.UUID, query_str: str
) -> list[MessageResponse]:
    match = await repository.get_match(db, match_id)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
        )

    _assert_participant(match, caller_id)

    if not query_str.strip():
        return []

    messages = await repository.search_messages(db, match_id, query_str.strip())
    return [MessageResponse.model_validate(m) for m in messages]
