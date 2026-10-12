import uuid

from fastapi import HTTPException, UploadFile, status
from geoalchemy2.elements import WKTElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import repository
from app.auth.schemas import (
    LoginRequest,
    ProfileUpdateRequest,
    SignupRequest,
    TokenResponse,
)
from app.shared.image_validation import validate_image
from app.shared.models import User
from app.shared.security import create_access_token, hash_password, verify_password
from app.shared.storage import PhotoStorage


async def signup(db: AsyncSession, data: SignupRequest) -> User:
    password_hash = hash_password(data.password)
    try:
        user = await repository.create_user(
            db, email=data.email, password_hash=password_hash, name=data.name
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc
    return user


async def login(db: AsyncSession, data: LoginRequest) -> TokenResponse:
    user = await repository.get_user_by_email(db, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)


async def get_profile(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return user


async def list_interests(db: AsyncSession) -> list:
    return await repository.list_interests(db)


async def update_profile(
    db: AsyncSession, user_id: uuid.UUID, data: ProfileUpdateRequest
) -> User:
    user = await get_profile(db, user_id)

    interests = await repository.get_interests_by_names(db, data.interests)
    found_names = {interest.name for interest in interests}
    unknown = set(data.interests) - found_names
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown interests: {', '.join(sorted(unknown))}",
        )

    user.bio = data.bio
    user.age = data.age
    user.gender = data.gender
    user.seeking = data.seeking
    user.age_min = data.age_min
    user.age_max = data.age_max
    if data.latitude is not None and data.longitude is not None:
        user.location = WKTElement(
            f"POINT({data.longitude} {data.latitude})", srid=4326
        )
    await repository.replace_user_interests(db, user, interests)
    await db.commit()
    return user


async def upload_photo(
    db: AsyncSession, user_id: uuid.UUID, file: UploadFile, storage: PhotoStorage
) -> User:
    user = await get_profile(db, user_id)
    data = await file.read()
    validate_image(data, file.content_type or "")
    key = await storage.upload(data, file.content_type or "")
    user.photo_key = key
    await db.commit()
    await db.refresh(user)
    return user
