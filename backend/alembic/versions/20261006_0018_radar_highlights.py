"""radar_results: title, company and highlights (why it matched), so results outlive the job

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("radar_results", sa.Column("title", sa.String(), nullable=True))
    op.add_column("radar_results", sa.Column("company", sa.String(), nullable=True))
    op.add_column(
        "radar_results",
        sa.Column("highlights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("radar_results", "highlights")
    op.drop_column("radar_results", "company")
    op.drop_column("radar_results", "title")
