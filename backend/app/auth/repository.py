from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import User


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
