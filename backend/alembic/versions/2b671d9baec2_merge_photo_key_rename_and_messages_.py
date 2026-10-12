"""merge photo_key rename and messages table

Revision ID: 2b671d9baec2
Revises: 4cf7f321e10c, cab730c95c29
Create Date: 2026-10-12 16:07:38.293243

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "2b671d9baec2"
down_revision: str | Sequence[str] | None = ("4cf7f321e10c", "cab730c95c29")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
