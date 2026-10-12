"""messages.meta: what a coach reply was grounded in (job version, steps, citations)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("meta", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "meta")
