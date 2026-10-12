"""add user location_label

Revision ID: 54f977295630
Revises: 2b671d9baec2
Create Date: 2026-10-12 16:08:07.749369

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "54f977295630"
down_revision: str | Sequence[str] | None = "2b671d9baec2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("location_label", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "location_label")
