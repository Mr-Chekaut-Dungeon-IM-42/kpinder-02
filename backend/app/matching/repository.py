import uuid
from datetime import datetime

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func

from app.shared.models import Match, Swipe, User


async def get_user_with_interests(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.interests))
    )
    return result.scalar_one_or_none()


async def user_exists(db: AsyncSession, user_id: uuid.UUID) -> bool:
    result = await db.execute(select(User.id).where(User.id == user_id))
    return result.scalar_one_or_none() is not None


async def get_candidates(
    db: AsyncSession, caller: User, radius_km: float, limit: int
) -> list[User]:
    already_swiped = exists(
        select(Swipe.id).where(Swipe.swiper_id == caller.id, Swipe.swiped_id == User.id)
    )

    conditions = [
        User.id != caller.id,
        User.location.isnot(None),
        func.ST_DWithin(User.location, caller.location, radius_km * 1000),
        ~already_swiped,
    ]

    if caller.seeking and caller.seeking != "everyone":
        conditions.append(User.gender == caller.seeking)
    if caller.gender:
        conditions.append(
            or_(
                User.seeking.is_(None),
                User.seeking == "everyone",
                User.seeking == caller.gender,
            )
        )
    if caller.age_min is not None:
        conditions.append(or_(User.age.is_(None), User.age >= caller.age_min))
    if caller.age_max is not None:
        conditions.append(or_(User.age.is_(None), User.age <= caller.age_max))

    result = await db.execute(
        select(User)
        .where(and_(*conditions))
        .options(selectinload(User.interests))
        .order_by(User.id)
        .limit(limit)
    )
    return list(result.scalars())


async def get_swipe(
    db: AsyncSession, swiper_id: uuid.UUID, swiped_id: uuid.UUID
) -> Swipe | None:
    result = await db.execute(
        select(Swipe).where(Swipe.swiper_id == swiper_id, Swipe.swiped_id == swiped_id)
    )
    return result.scalar_one_or_none()


async def create_swipe(
    db: AsyncSession, swiper_id: uuid.UUID, swiped_id: uuid.UUID, decision: str
) -> Swipe:
    swipe = Swipe(swiper_id=swiper_id, swiped_id=swiped_id, decision=decision)
    db.add(swipe)
    await db.flush()
    return swipe


def normalize_pair(user_a: uuid.UUID, user_b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (user_a, user_b) if str(user_a) < str(user_b) else (user_b, user_a)


async def get_match_between(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> Match | None:
    a, b = normalize_pair(user_a, user_b)
    result = await db.execute(
        select(Match).where(Match.user_a_id == a, Match.user_b_id == b)
    )
    return result.scalar_one_or_none()


async def create_match(db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> Match:
    a, b = normalize_pair(user_a, user_b)
    match = Match(user_a_id=a, user_b_id=b)
    db.add(match)
    await db.flush()
    return match


async def get_matches_page(
    db: AsyncSession,
    user_id: uuid.UUID,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
    limit: int,
) -> list[Match]:
    conditions = [or_(Match.user_a_id == user_id, Match.user_b_id == user_id)]
    if cursor_created_at is not None and cursor_id is not None:
        conditions.append(
            or_(
                Match.created_at < cursor_created_at,
                and_(Match.created_at == cursor_created_at, Match.id < cursor_id),
            )
        )
    result = await db.execute(
        select(Match)
        .where(and_(*conditions))
        .order_by(Match.created_at.desc(), Match.id.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def get_users_by_ids(
    db: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    result = await db.execute(select(User).where(User.id.in_(ids)))
    return {user.id: user for user in result.scalars()}
