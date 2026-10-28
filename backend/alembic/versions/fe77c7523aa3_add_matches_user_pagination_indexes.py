"""add_matches_user_pagination_indexes

Revision ID: fe77c7523aa3
Revises: 54f977295630
Create Date: 2026-10-27 14:34:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe77c7523aa3"
down_revision: str | Sequence[str] | None = "54f977295630"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NOTE: autogenerate also flagged the postgis tiger-geocoder tables (noise,
# same as the initial migration) and a spurious unnamed-constraint diff on
# user_interests — both stripped by hand per ADR-0008.


def upgrade() -> None:
    op.create_index(
        "ix_matches_user_a_created_at",
        "matches",
        ["user_a_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_matches_user_b_created_at",
        "matches",
        ["user_b_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_matches_user_b_created_at", table_name="matches")
    op.drop_index("ix_matches_user_a_created_at", table_name="matches")
