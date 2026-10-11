"""letters.ideas: writing ideas shown beside the blocks of a letter the user writes themself

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("letters", sa.Column("ideas", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("letters", "ideas")
