"""users.weekly_goal: optional weekly application goal (null = off)

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("weekly_goal", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "weekly_goal")
