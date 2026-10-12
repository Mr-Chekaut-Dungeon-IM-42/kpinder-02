"""rename user photo_url to photo_key

Revision ID: 4cf7f321e10c
Revises: 6debd7fefb1b
Create Date: 2026-10-12 15:57:57.763142

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4cf7f321e10c"
down_revision: str | Sequence[str] | None = "6debd7fefb1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The bucket moved from public-URL storage to presigned-URL storage (private
# bucket), so the column now holds an R2 object key, not a full URL —
# renamed to match what it actually stores.


def upgrade() -> None:
    op.alter_column("users", "photo_url", new_column_name="photo_key")


def downgrade() -> None:
    op.alter_column("users", "photo_key", new_column_name="photo_url")
