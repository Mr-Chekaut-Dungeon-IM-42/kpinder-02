from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.shared.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def signup(
    data: SignupRequest, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    user = await service.signup(db, data)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    return await service.login(db, data)
