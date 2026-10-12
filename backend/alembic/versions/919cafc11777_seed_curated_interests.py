"""seed curated interests

Revision ID: 919cafc11777
Revises: a35345853a4b
Create Date: 2026-10-12 10:53:10.663409

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.sql import table

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "919cafc11777"
down_revision: str | Sequence[str] | None = "a35345853a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INTERESTS = [
    "hiking",
    "travel",
    "photography",
    "cooking",
    "baking",
    "gaming",
    "reading",
    "movies",
    "music",
    "dancing",
    "yoga",
    "fitness",
    "running",
    "cycling",
    "swimming",
    "art",
    "painting",
    "writing",
    "coffee",
    "wine",
    "cocktails",
    "foodie",
    "pets",
    "dogs",
    "cats",
    "nature",
    "camping",
    "meditation",
    "tech",
    "startups",
    "volunteering",
    "languages",
]

interests_table = table(
    "interests", sa.column("id", sa.UUID()), sa.column("name", sa.String())
)


def upgrade() -> None:
    op.bulk_insert(
        interests_table,
        [{"id": uuid.uuid4(), "name": name} for name in INTERESTS],
    )


def downgrade() -> None:
    op.execute(interests_table.delete().where(interests_table.c.name.in_(INTERESTS)))
