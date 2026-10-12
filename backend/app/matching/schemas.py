import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CandidateResponse(BaseModel):
    id: uuid.UUID
    name: str
    age: int | None
    bio: str | None
    photo_url: str | None
    interests: list[str]

    model_config = {"from_attributes": True}


class SwipeRequest(BaseModel):
    target_id: uuid.UUID
    decision: Literal["like", "pass"]


class SwipeResponse(BaseModel):
    matched: bool
    match_id: uuid.UUID | None = None


class MatchUser(BaseModel):
    id: uuid.UUID
    name: str
    photo_url: str | None


class MatchResponse(BaseModel):
    match_id: uuid.UUID
    created_at: datetime
    other_user: MatchUser


class MatchesPage(BaseModel):
    items: list[MatchResponse]
    next_cursor: str | None = None
