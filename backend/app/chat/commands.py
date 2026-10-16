import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import repository
from app.chat.common import assert_participant
from app.chat.schemas import (
    MessageEditRequest,
    MessageResponse,
    MessageSendRequest,
)
from app.shared.db import get_db
from app.shared.ws import ConnectionManager, ws_manager


class SendMessageCommand:
    def __init__(self, db: AsyncSession, ws: ConnectionManager = ws_manager) -> None:
        self.db = db
        self.ws = ws

    async def execute(
        self,
        caller_id: uuid.UUID,
        match_id: uuid.UUID,
        data: MessageSendRequest,
    ) -> MessageResponse:
        match = await repository.get_match(self.db, match_id)
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Match not found"
            )

        recipient_id = assert_participant(match, caller_id)

        try:
            message = await repository.create_message(
                self.db, match_id, caller_id, data.client_message_id, data.content
            )
            await self.db.commit()
            is_new = True
        except IntegrityError:
            await self.db.rollback()
            existing = await repository.get_message_by_client_id(
                self.db, match_id, caller_id, data.client_message_id
            )
            if existing is None:
                raise
            message = existing
            is_new = False

        response = MessageResponse.model_validate(message)
        if is_new:
            await self.ws.send_event(
                recipient_id, "new_message", response.model_dump(mode="json")
            )

        return response


class EditMessageCommand:
    def __init__(self, db: AsyncSession, ws: ConnectionManager = ws_manager) -> None:
        self.db = db
        self.ws = ws

    async def execute(
        self,
        caller_id: uuid.UUID,
        message_id: uuid.UUID,
        data: MessageEditRequest,
    ) -> MessageResponse:
        message = await repository.get_message_by_id(self.db, message_id)
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
            )

        if message.sender_id != caller_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot edit another user's message",
            )

        match = await repository.get_match(self.db, message.match_id)
        recipient_id = assert_participant(match, caller_id) if match else None

        updated = await repository.update_message(self.db, message, data.content)
        await self.db.commit()

        response = MessageResponse.model_validate(updated)
        if recipient_id:
            await self.ws.send_event(
                recipient_id, "message_edited", response.model_dump(mode="json")
            )

        return response


class DeleteMessageCommand:
    def __init__(self, db: AsyncSession, ws: ConnectionManager = ws_manager) -> None:
        self.db = db
        self.ws = ws

    async def execute(self, caller_id: uuid.UUID, message_id: uuid.UUID) -> None:
        message = await repository.get_message_by_id(self.db, message_id)
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
        match = await repository.get_match(self.db, match_id)
        recipient_id = assert_participant(match, caller_id) if match else None

        await repository.delete_message(self.db, message)
        await self.db.commit()

        if recipient_id:
            await self.ws.send_event(
                recipient_id,
                "message_deleted",
                {"id": str(message_id), "match_id": str(match_id)},
            )


def get_send_message_command(
    db: AsyncSession = Depends(get_db),
) -> SendMessageCommand:
    return SendMessageCommand(db=db)


def get_edit_message_command(
    db: AsyncSession = Depends(get_db),
) -> EditMessageCommand:
    return EditMessageCommand(db=db)


def get_delete_message_command(
    db: AsyncSession = Depends(get_db),
) -> DeleteMessageCommand:
    return DeleteMessageCommand(db=db)
