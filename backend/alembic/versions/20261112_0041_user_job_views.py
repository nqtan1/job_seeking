"""users.job_views: saved Jobs filters live on the account, not in localStorage

Revision ID: 0041
Revises: 0039
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0041"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("job_views", JSONB, server_default="[]", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("users", "job_views")
