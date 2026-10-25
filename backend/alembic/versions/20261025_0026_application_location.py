"""applications.location: where the role is (copied from the job, editable)

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("location", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "location")
