"""index ai_calls by (user_id, created_at) for the per-call quota count

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_ai_calls_user_id_created_at", "ai_calls", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_calls_user_id_created_at", table_name="ai_calls")
