"""swipes and matches

Revision ID: 6debd7fefb1b
Revises: 919cafc11777
Create Date: 2026-10-12 11:15:45.446197

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6debd7fefb1b"
down_revision: str | Sequence[str] | None = "919cafc11777"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NOTE: autogenerate also flagged the postgis tiger-geocoder tables (noise,
# same as the initial migration) and a spurious unnamed-constraint diff on
# user_interests (a Postgres constraint-naming artifact, not a real schema
# change) — both stripped by hand per ADR-0008.


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_a_id", sa.UUID(), nullable=False),
        sa.Column("user_b_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_a_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_b_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_a_id", "user_b_id"),
    )
    op.create_index(
        "ix_matches_created_at_id", "matches", ["created_at", "id"], unique=False
    )
    op.create_table(
        "swipes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("swiper_id", sa.UUID(), nullable=False),
        sa.Column("swiped_id", sa.UUID(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["swiped_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["swiper_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("swiper_id", "swiped_id"),
    )


def downgrade() -> None:
    op.drop_table("swipes")
    op.drop_index("ix_matches_created_at_id", table_name="matches")
    op.drop_table("matches")
