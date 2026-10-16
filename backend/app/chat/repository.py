import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.shared.models import Match, Message


async def get_match(db: AsyncSession, match_id: uuid.UUID) -> Match | None:
    result = await db.execute(select(Match).where(Match.id == match_id))
    return result.scalar_one_or_none()


async def create_message(
    db: AsyncSession,
    match_id: uuid.UUID,
    sender_id: uuid.UUID,
    client_message_id: uuid.UUID,
    content: str,
) -> Message:
    message = Message(
        match_id=match_id,
        sender_id=sender_id,
        client_message_id=client_message_id,
        content=content,
    )
    db.add(message)
    await db.flush()
    return message


async def get_message_by_client_id(
    db: AsyncSession,
    match_id: uuid.UUID,
    sender_id: uuid.UUID,
    client_message_id: uuid.UUID,
) -> Message | None:
    stmt = select(Message).where(
        Message.match_id == match_id,
        Message.sender_id == sender_id,
        Message.client_message_id == client_message_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_message_by_id(db: AsyncSession, message_id: uuid.UUID) -> Message | None:
    result = await db.execute(select(Message).where(Message.id == message_id))
    return result.scalar_one_or_none()


async def get_messages_page(
    db: AsyncSession,
    match_id: uuid.UUID,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
    limit: int = 20,
) -> list[Message]:
    conditions = [Message.match_id == match_id]
    if cursor_created_at is not None and cursor_id is not None:
        conditions.append(
            or_(
                Message.created_at < cursor_created_at,
                and_(Message.created_at == cursor_created_at, Message.id < cursor_id),
            )
        )
    stmt = (
        select(Message)
        .where(and_(*conditions))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars())


async def update_message(db: AsyncSession, message: Message, content: str) -> Message:
    message.content = content
    message.edited_at = func.now()
    await db.flush()
    await db.refresh(message)
    return message


async def delete_message(db: AsyncSession, message: Message) -> None:
    await db.delete(message)
    await db.flush()


async def search_messages(
    db: AsyncSession, match_id: uuid.UUID, query_str: str
) -> list[Message]:
    stmt = (
        select(Message)
        .where(
            Message.match_id == match_id,
            Message.content.ilike(f"%{query_str}%"),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars())
