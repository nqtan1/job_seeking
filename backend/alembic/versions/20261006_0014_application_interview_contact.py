"""applications.interview_at and applications.contact

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("interview_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("applications", sa.Column("contact", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "contact")
    op.drop_column("applications", "interview_at")
