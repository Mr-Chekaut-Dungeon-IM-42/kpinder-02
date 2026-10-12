import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageSendRequest(BaseModel):
    client_message_id: uuid.UUID
    content: str = Field(min_length=1, max_length=2000)


class MessageEditRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    sender_id: uuid.UUID
    client_message_id: uuid.UUID
    content: str
    created_at: datetime
    edited_at: datetime | None = None


class MessagesPage(BaseModel):
    items: list[MessageResponse]
    next_cursor: str | None = None
