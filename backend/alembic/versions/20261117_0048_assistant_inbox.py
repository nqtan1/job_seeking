"""conversations.kind (ADR 0042): 'assistant' marks the one Assistant conversation per org, where
flow run results and reminders land; every existing conversation is a 'chat'.

Revision ID: 0048
Revises: 0047
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("kind", sa.String(16), server_default="chat", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_conversations_kind"), "conversations", "kind IN ('chat', 'assistant')"
    )
    op.create_index(
        "uq_conversations_org_id_assistant",
        "conversations",
        ["org_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'assistant'"),
    )


def downgrade() -> None:
    # the inbox messages stay, in what becomes an ordinary chat
    op.drop_index("uq_conversations_org_id_assistant", table_name="conversations")
    op.drop_constraint(op.f("ck_conversations_kind"), "conversations", type_="check")
    op.drop_column("conversations", "kind")
