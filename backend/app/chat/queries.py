import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import repository
from app.chat.common import assert_participant, decode_cursor, encode_cursor
from app.chat.schemas import (
    MessageResponse,
    MessagesPage,
)
from app.shared.db import get_db


class GetMessagesQuery:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(
        self,
        caller_id: uuid.UUID,
        match_id: uuid.UUID,
        cursor: str | None,
        limit: int = 20,
    ) -> MessagesPage:
        match = await repository.get_match(self.db, match_id)
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
            )

        assert_participant(match, caller_id)

        cursor_created_at, cursor_id = (None, None)
        if cursor is not None:
            cursor_created_at, cursor_id = decode_cursor(cursor)

        messages = await repository.get_messages_page(
            self.db, match_id, cursor_created_at, cursor_id, limit
        )

        next_cursor = None
        if len(messages) == limit:
            next_cursor = encode_cursor(messages[-1].created_at, messages[-1].id)

        return MessagesPage(
            items=[MessageResponse.model_validate(m) for m in messages],
            next_cursor=next_cursor,
        )


class SearchMessagesQuery:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(
        self, caller_id: uuid.UUID, match_id: uuid.UUID, query_str: str
    ) -> list[MessageResponse]:
        match = await repository.get_match(self.db, match_id)
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
            )

        assert_participant(match, caller_id)

        if not query_str.strip():
            return []

        messages = await repository.search_messages(
            self.db, match_id, query_str.strip()
        )
        return [MessageResponse.model_validate(m) for m in messages]


def get_messages_query(
    db: AsyncSession = Depends(get_db),
) -> GetMessagesQuery:
    return GetMessagesQuery(db=db)


def get_search_messages_query(
    db: AsyncSession = Depends(get_db),
) -> SearchMessagesQuery:
    return SearchMessagesQuery(db=db)
