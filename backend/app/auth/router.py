import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.auth.commands import (
    LoginCommand,
    SignupCommand,
    UpdateProfileCommand,
    UploadPhotoCommand,
    get_login_command,
    get_signup_command,
    get_update_profile_command,
    get_upload_photo_command,
)
from app.auth.queries import (
    GetProfileQuery,
    ListInterestsQuery,
    get_list_interests_query,
    get_profile_query,
)
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
    data: SignupRequest,
    command: SignupCommand = Depends(get_signup_command),
) -> UserResponse:
    user = await command.execute(data)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    command: LoginCommand = Depends(get_login_command),
) -> TokenResponse:
    return await command.execute(data)


@router.get("/interests", response_model=list[InterestResponse])
async def interests(
    query: ListInterestsQuery = Depends(get_list_interests_query),
) -> list[InterestResponse]:
    rows = await query.execute()
    return [InterestResponse.model_validate(row) for row in rows]


@router.get("/me", response_model=ProfileResponse)
async def me(
    user_id: uuid.UUID = Depends(get_current_user_id),
    query: GetProfileQuery = Depends(get_profile_query),
) -> ProfileResponse:
    user = await query.execute(user_id)
    return await _to_profile_response(user)


@router.patch("/update_profile", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    command: UpdateProfileCommand = Depends(get_update_profile_command),
) -> ProfileResponse:
    user = await command.execute(user_id, data)
    return await _to_profile_response(user)


@router.post("/upload_photo", response_model=PhotoResponse)
async def upload_photo(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
    command: UploadPhotoCommand = Depends(get_upload_photo_command),
    storage: PhotoStorage = Depends(get_photo_storage),
) -> PhotoResponse:
    user = await command.execute(user_id, file)
    photo_url = await storage.get_url(user.photo_key)
    return PhotoResponse(photo_url=photo_url)
