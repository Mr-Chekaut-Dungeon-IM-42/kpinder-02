import uuid

from fastapi import Depends, HTTPException, UploadFile, status
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
from app.shared.db import get_db
from app.shared.image_validation import validate_image
from app.shared.models import User
from app.shared.security import create_access_token, hash_password, verify_password
from app.shared.storage import PhotoStorage, get_photo_storage


class SignupCommand:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, data: SignupRequest) -> User:
        password_hash = hash_password(data.password)
        try:
            user = await repository.create_user(
                self.db, email=data.email, password_hash=password_hash, name=data.name
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from exc
        return user


class LoginCommand:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, data: LoginRequest) -> TokenResponse:
        user = await repository.get_user_by_email(self.db, data.email)
        if user is None or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        token = create_access_token(subject=str(user.id))
        return TokenResponse(access_token=token)


class UpdateProfileCommand:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, user_id: uuid.UUID, data: ProfileUpdateRequest) -> User:
        user = await repository.get_user_by_id(self.db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )

        interests = await repository.get_interests_by_names(self.db, data.interests)
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
            user.location_label = data.location_label
        await repository.replace_user_interests(self.db, user, interests)
        await self.db.commit()
        return user


class UploadPhotoCommand:
    def __init__(self, db: AsyncSession, storage: PhotoStorage | None = None) -> None:
        self.db = db
        self.storage = storage or get_photo_storage()

    async def execute(self, user_id: uuid.UUID, file: UploadFile) -> User:
        user = await repository.get_user_by_id(self.db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )

        data = await file.read()
        validate_image(data, file.content_type or "")
        key = await self.storage.upload(data, file.content_type or "")
        user.photo_key = key
        await self.db.commit()
        await self.db.refresh(user)
        return user


def get_signup_command(db: AsyncSession = Depends(get_db)) -> SignupCommand:
    return SignupCommand(db=db)


def get_login_command(db: AsyncSession = Depends(get_db)) -> LoginCommand:
    return LoginCommand(db=db)


def get_update_profile_command(
    db: AsyncSession = Depends(get_db),
) -> UpdateProfileCommand:
    return UpdateProfileCommand(db=db)


def get_upload_photo_command(
    db: AsyncSession = Depends(get_db),
    storage: PhotoStorage = Depends(get_photo_storage),
) -> UploadPhotoCommand:
    return UploadPhotoCommand(db=db, storage=storage)
