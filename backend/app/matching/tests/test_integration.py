import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.matching import repository
from app.shared.models import Match, User

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_concurrent_match_creation_results_in_exactly_one_match(
    session_factory,
):
    """Exercises the race ADR-0009 describes directly at the point it
    actually occurs: two concurrent transactions both detecting a reciprocal
    like and both attempting to insert the same normalized Match pair. Both
    Swipe rows are pre-seeded (committed) so the test isn't at the mercy of
    whether the app-level interleaving of two fresh service.swipe() calls
    happens to line up — it forces the real contended case, the Match
    unique-constraint insert itself.
    """
    user_a_id, user_b_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as db:
        db.add(
            User(
                id=user_a_id,
                email=f"a_{user_a_id.hex[:6]}@b.com",
                password_hash="x",
                name="A",
            )
        )
        db.add(
            User(
                id=user_b_id,
                email=f"b_{user_b_id.hex[:6]}@b.com",
                password_hash="x",
                name="B",
            )
        )
        await db.commit()

    async with session_factory() as db:
        await repository.create_swipe(db, user_a_id, user_b_id, "like")
        await repository.create_swipe(db, user_b_id, user_a_id, "like")
        await db.commit()

    async def detect_and_create_match(user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
        async with session_factory() as db:
            try:
                await repository.create_match(db, user_a, user_b)
                await db.commit()
                return True
            except IntegrityError:
                await db.rollback()
                match = await repository.get_match_between(db, user_a, user_b)
                return match is not None

    results = await asyncio.gather(
        detect_and_create_match(user_a_id, user_b_id),
        detect_and_create_match(user_b_id, user_a_id),
    )

    assert results == [True, True]

    async with session_factory() as db:
        matches = (
            (
                await db.execute(
                    select(Match).where(
                        (Match.user_a_id == user_a_id) & (Match.user_b_id == user_b_id)
                        | (Match.user_a_id == user_b_id)
                        & (Match.user_b_id == user_a_id)
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(matches) == 1
