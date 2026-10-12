import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.schemas import (
    InterestResponse,
    LoginRequest,
    PhotoResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.shared.db import get_db
from app.shared.jwt_dep import get_current_user_id
from app.shared.models import User
from app.shared.storage import PhotoStorage, get_photo_storage, resolve_photo_url

router = APIRouter(prefix="/auth", tags=["auth"])


async def _to_profile_response(user: User) -> ProfileResponse:
    photo_url = None
    if user.photo_key is not None:
        photo_url = await resolve_photo_url(get_photo_storage(), user.photo_key)
    return ProfileResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        bio=user.bio,
        age=user.age,
        gender=user.gender,
        seeking=user.seeking,
        age_min=user.age_min,
        age_max=user.age_max,
        photo_url=photo_url,
        interests=[ui.interest.name for ui in user.interests],
        has_location=user.location is not None,
        location_label=user.location_label,
    )


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


@router.get("/interests", response_model=list[InterestResponse])
async def interests(db: AsyncSession = Depends(get_db)) -> list[InterestResponse]:
    rows = await service.list_interests(db)
    return [InterestResponse.model_validate(row) for row in rows]


@router.get("/me", response_model=ProfileResponse)
async def me(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ProfileResponse:
    user = await service.get_profile(db, user_id)
    return await _to_profile_response(user)


@router.patch("/update_profile", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ProfileResponse:
    user = await service.update_profile(db, user_id, data)
    return await _to_profile_response(user)


@router.post("/upload_photo", response_model=PhotoResponse)
async def upload_photo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    storage: PhotoStorage = Depends(get_photo_storage),
) -> PhotoResponse:
    user = await service.upload_photo(db, user_id, file, storage)
    photo_url = await storage.get_url(user.photo_key)
    return PhotoResponse(photo_url=photo_url)
