"""agent chat (ADR 0039): conversations.agent_id (null = the default coach) and
agent_versions.tools (registry ids a helper may call in chat)

Revision ID: 0044
Revises: 0043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("agent_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_agent_id_agents",
        "conversations",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "agent_versions",
        sa.Column(
            "tools",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    # existing helpers get the coach's chat tools, like a new version (literal: a migration
    # never imports app code, which may change after it)
    op.execute(
        """UPDATE agent_versions SET tools = '["profile_read", "job_lookup", "fit_read", "web_search"]'"""
    )


def downgrade() -> None:
    op.drop_column("agent_versions", "tools")
    op.drop_constraint(
        "fk_conversations_agent_id_agents", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "agent_id")
