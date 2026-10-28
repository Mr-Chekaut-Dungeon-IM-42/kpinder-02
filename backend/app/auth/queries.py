import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import repository
from app.shared.db import get_db
from app.shared.models import User


class GetProfileQuery:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, user_id: uuid.UUID) -> User:
        user = await repository.get_user_by_id(self.db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )
        return user


class ListInterestsQuery:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self) -> list:
        return await repository.list_interests(self.db)


def get_profile_query(db: AsyncSession = Depends(get_db)) -> GetProfileQuery:
    return GetProfileQuery(db=db)


def get_list_interests_query(
    db: AsyncSession = Depends(get_db),
) -> ListInterestsQuery:
    return ListInterestsQuery(db=db)
