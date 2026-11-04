"""index ai_calls.created_at for the global daily cap

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_ai_calls_created_at", "ai_calls", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_calls_created_at", table_name="ai_calls")
