import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import Interest, User, UserInterest


async def create_user(
    db: AsyncSession, *, email: str, password_hash: str, name: str
) -> User:
    user = User(email=email, password_hash=password_hash, name=name)
    db.add(user)
    await db.flush()
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.interests))
    )
    return result.scalar_one_or_none()


async def list_interests(db: AsyncSession) -> list[Interest]:
    result = await db.execute(select(Interest).order_by(Interest.name))
    return list(result.scalars())


async def get_interests_by_names(db: AsyncSession, names: list[str]) -> list[Interest]:
    if not names:
        return []
    result = await db.execute(select(Interest).where(Interest.name.in_(names)))
    return list(result.scalars())


async def replace_user_interests(
    db: AsyncSession, user: User, interests: list[Interest]
) -> None:
    user.interests = [UserInterest(interest=interest) for interest in interests]
    await db.flush()
