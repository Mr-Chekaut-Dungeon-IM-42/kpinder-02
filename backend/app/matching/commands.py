import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching import repository
from app.matching.schemas import SwipeRequest, SwipeResponse
from app.shared.db import get_db


class SwipeCommand:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(self, caller_id: uuid.UUID, data: SwipeRequest) -> SwipeResponse:
        if data.target_id == caller_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Cannot swipe on yourself",
            )
        if not await repository.user_exists(self.db, data.target_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )

        try:
            await repository.create_swipe(
                self.db, caller_id, data.target_id, data.decision
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            existing = await repository.get_swipe(self.db, caller_id, data.target_id)
            if existing is None or existing.decision != data.decision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Swipe decision already recorded and cannot be changed",
                ) from exc
            match = await repository.get_match_between(
                self.db, caller_id, data.target_id
            )
            return SwipeResponse(
                matched=match is not None, match_id=match.id if match else None
            )

        if data.decision == "pass":
            return SwipeResponse(matched=False)

        reciprocal = await repository.get_swipe(self.db, data.target_id, caller_id)
        if reciprocal is None or reciprocal.decision != "like":
            return SwipeResponse(matched=False)

        try:
            match = await repository.create_match(self.db, caller_id, data.target_id)
            await self.db.commit()
            return SwipeResponse(matched=True, match_id=match.id)
        except IntegrityError:
            await self.db.rollback()
            match = await repository.get_match_between(
                self.db, caller_id, data.target_id
            )
            return SwipeResponse(matched=True, match_id=match.id if match else None)


def get_swipe_command(db: AsyncSession = Depends(get_db)) -> SwipeCommand:
    return SwipeCommand(db=db)
