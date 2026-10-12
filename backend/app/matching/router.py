import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching import service
from app.matching.schemas import (
    CandidateResponse,
    MatchesPage,
    SwipeRequest,
    SwipeResponse,
)
from app.shared.db import get_db
from app.shared.jwt_dep import get_current_user_id

router = APIRouter(prefix="/matching", tags=["matching"])


@router.get("/feed", response_model=list[CandidateResponse])
async def feed(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[CandidateResponse]:
    return await service.get_feed(db, user_id)


@router.post("/swipe", response_model=SwipeResponse)
async def swipe(
    data: SwipeRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> SwipeResponse:
    return await service.swipe(db, user_id, data)


@router.get("/matches", response_model=MatchesPage)
async def matches(
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MatchesPage:
    return await service.get_matches(db, user_id, cursor)
