import uuid

from fastapi import APIRouter, Depends, Query

from app.matching.commands import SwipeCommand, get_swipe_command
from app.matching.queries import (
    GetFeedQuery,
    GetMatchesQuery,
    get_feed_query,
    get_matches_query,
)
from app.matching.schemas import (
    CandidateResponse,
    MatchesPage,
    SwipeRequest,
    SwipeResponse,
)
from app.shared.jwt_dep import get_current_user_id

router = APIRouter(prefix="/matching", tags=["matching"])


@router.get("/feed", response_model=list[CandidateResponse])
async def feed(
    user_id: uuid.UUID = Depends(get_current_user_id),
    query: GetFeedQuery = Depends(get_feed_query),
) -> list[CandidateResponse]:
    return await query.execute(user_id)


@router.post("/swipe", response_model=SwipeResponse)
async def swipe(
    data: SwipeRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    command: SwipeCommand = Depends(get_swipe_command),
) -> SwipeResponse:
    return await command.execute(user_id, data)


@router.get("/matches", response_model=MatchesPage)
async def matches(
    cursor: str | None = Query(default=None),
    user_id: uuid.UUID = Depends(get_current_user_id),
    query: GetMatchesQuery = Depends(get_matches_query),
) -> MatchesPage:
    return await query.execute(user_id, cursor)
