"""rate_hits (ADR 0041): per-user rate-limit counters shared by every API instance, one row per
key and fixed window; rows older than a day are deleted by the daily sweep

Revision ID: 0045
Revises: 0044
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_hits",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key", "window_start", name="pk_rate_hits"),
    )


def downgrade() -> None:
    op.drop_table("rate_hits")
