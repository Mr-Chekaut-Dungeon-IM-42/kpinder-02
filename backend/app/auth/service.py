from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import repository
from app.auth.schemas import LoginRequest, SignupRequest, TokenResponse
from app.shared.models import User
from app.shared.security import create_access_token, hash_password, verify_password


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
