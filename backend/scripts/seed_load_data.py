"""Seeds the DB with a realistic-scale dataset for load testing and EXPLAIN ANALYZE.

Bypasses the SQLAlchemy ORM and app layer entirely — this is throwaway local
load-test fixture data, not something the app's business rules need to validate.
Uses asyncpg directly, batched, for bulk-insert speed at tens of thousands of rows.

Usage (against the local docker-compose db — port overridden to avoid a clash
with another local project already on 5432; see `make load`):

    uv run python scripts/seed_load_data.py \
        --database-url postgresql://kpinder:kpinder@127.0.0.2:5433/kpinder \
        --users 50000
"""

import argparse
import asyncio
import math
import random
import uuid

import asyncpg
from argon2 import PasswordHasher

CITIES = [
    ("Kyiv", 50.4501, 30.5234),
    ("Lviv", 49.8397, 24.0297),
    ("Odesa", 46.4825, 30.7233),
    ("Kharkiv", 49.9935, 36.2304),
    ("Dnipro", 48.4647, 35.0462),
]
GENDERS = ["male", "female"]
SEEKING = ["male", "female", "everyone"]
LOAD_TEST_PASSWORD = "LoadTest123!"
BATCH_SIZE = 2000


def jittered_point(lat: float, lon: float) -> tuple[float, float]:
    # ~0.3 deg std dev ≈ up to ~30km jitter, so candidate queries at a 50km
    # radius return a realistically large, non-trivial candidate set.
    lat_j = lat + random.gauss(0, 0.3)
    lon_j = lon + random.gauss(0, 0.3 / max(math.cos(math.radians(lat)), 0.1))
    return lat_j, lon_j


async def seed(users_n: int, swipes_per_user: int, database_url: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        interest_ids = [r["id"] for r in await conn.fetch("SELECT id FROM interests")]
        if not interest_ids:
            raise RuntimeError(
                "No curated interests found — run `alembic upgrade head` first"
            )

        password_hash = PasswordHasher().hash(LOAD_TEST_PASSWORD)

        print(f"Seeding {users_n} users...")
        user_ids: list[uuid.UUID] = [uuid.uuid4() for _ in range(users_n)]
        for start in range(0, users_n, BATCH_SIZE):
            batch_ids = user_ids[start : start + BATCH_SIZE]
            rows = []
            interest_rows = []
            for i, uid in zip(
                range(start, start + len(batch_ids)), batch_ids, strict=True
            ):
                city_name, lat, lon = random.choice(CITIES)
                ulat, ulon = jittered_point(lat, lon)
                rows.append(
                    (
                        uid,
                        f"load_user_{i}@loadtest.kpinderapp.com",
                        password_hash,
                        f"Load User {i}",
                        random.randint(18, 55),
                        "Seeded load-test profile.",
                        random.choice(GENDERS),
                        random.choice(SEEKING),
                        18,
                        55,
                        ulon,
                        ulat,
                        city_name,
                    )
                )
                for interest_id in random.sample(interest_ids, k=random.randint(3, 8)):
                    interest_rows.append((uid, interest_id))

            await conn.executemany(
                """
                INSERT INTO users (
                    id, email, password_hash, name, age, bio, gender, seeking,
                    age_min, age_max, location, location_label
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    ST_SetSRID(ST_MakePoint($11, $12), 4326)::geography, $13
                )
                """,
                rows,
            )
            await conn.executemany(
                "INSERT INTO user_interests (user_id, interest_id) VALUES ($1, $2)",
                interest_rows,
            )
            print(f"  users {start + len(batch_ids)}/{users_n}")

        print(f"Seeding ~{swipes_per_user} swipes per user...")
        total_swipes = 0
        for start in range(0, users_n, BATCH_SIZE):
            batch_ids = user_ids[start : start + BATCH_SIZE]
            swipe_rows = []
            seen_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
            for swiper in batch_ids:
                targets = random.sample(user_ids, k=min(swipes_per_user, users_n - 1))
                for target in targets:
                    if target == swiper or (swiper, target) in seen_pairs:
                        continue
                    seen_pairs.add((swiper, target))
                    decision = "like" if random.random() < 0.6 else "pass"
                    swipe_rows.append((uuid.uuid4(), swiper, target, decision))
            try:
                await conn.executemany(
                    """
                    INSERT INTO swipes (id, swiper_id, swiped_id, decision)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING
                    """,
                    swipe_rows,
                )
            except asyncpg.PostgresError as exc:
                print(f"  batch swipe insert warning: {exc}")
            total_swipes += len(swipe_rows)
            print(f"  swipes {start + len(batch_ids)}/{users_n} users processed")

        print(f"Inserted ~{total_swipes} swipe rows. Deriving reciprocal matches...")
        match_result = await conn.execute(
            """
            INSERT INTO matches (id, user_a_id, user_b_id)
            SELECT DISTINCT ON (
                LEAST(s1.swiper_id, s1.swiped_id), GREATEST(s1.swiper_id, s1.swiped_id)
            )
                gen_random_uuid(),
                LEAST(s1.swiper_id, s1.swiped_id),
                GREATEST(s1.swiper_id, s1.swiped_id)
            FROM swipes s1
            JOIN swipes s2
                ON s2.swiper_id = s1.swiped_id AND s2.swiped_id = s1.swiper_id
            WHERE s1.decision = 'like' AND s2.decision = 'like'
            ON CONFLICT DO NOTHING
            """
        )
        print(f"  {match_result}")

        print("Seeding a handful of messages per match...")
        matches = await conn.fetch("SELECT id, user_a_id, user_b_id FROM matches")
        message_rows = []
        for m in matches:
            n_messages = random.randint(0, 20)
            senders = [m["user_a_id"], m["user_b_id"]]
            for _ in range(n_messages):
                message_rows.append(
                    (
                        uuid.uuid4(),
                        m["id"],
                        random.choice(senders),
                        uuid.uuid4(),
                        "Seeded load-test message content.",
                    )
                )
        for start in range(0, len(message_rows), BATCH_SIZE):
            chunk = message_rows[start : start + BATCH_SIZE]
            await conn.executemany(
                """
                INSERT INTO messages
                    (id, match_id, sender_id, client_message_id, content)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT DO NOTHING
                """,
                chunk,
            )
        print(f"  {len(message_rows)} messages across {len(matches)} matches")

        counts = await conn.fetchrow(
            """
            SELECT
                (SELECT count(*) FROM users) AS users,
                (SELECT count(*) FROM swipes) AS swipes,
                (SELECT count(*) FROM matches) AS matches,
                (SELECT count(*) FROM messages) AS messages
            """
        )
        print(f"Done. Final counts: {dict(counts)}")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default="postgresql://kpinder:kpinder@127.0.0.2:5432/kpinder",
        help="Plain (non-SQLAlchemy) asyncpg DSN — note: no '+asyncpg' scheme suffix.",
    )
    parser.add_argument("--users", type=int, default=50_000)
    parser.add_argument(
        "--swipes-per-user",
        type=int,
        default=40,
        help="Each user swipes roughly this many random others.",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.users, args.swipes_per_user, args.database_url))


if __name__ == "__main__":
    main()
