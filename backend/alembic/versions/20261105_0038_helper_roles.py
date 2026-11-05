"""agent_versions.role: built-in helper roles with a locked default prompt (ADR 0035)

Revision ID: 0038
Revises: 0037
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_versions",
        sa.Column(
            "role", sa.String(length=16), server_default="custom", nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_agent_versions_role"),
        "agent_versions",
        "role IN ('custom', 'letter', 'interview', 'cv_advice')",
    )
    op.drop_constraint(
        op.f("ck_agent_versions_instructions"), "agent_versions", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_agent_versions_instructions"),
        "agent_versions",
        "char_length(instructions) <= 4000 AND (role <> 'custom' OR char_length(instructions) >= 1)",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agent_versions SET instructions = 'Do the task.' WHERE instructions = ''"
    )
    op.drop_constraint(
        op.f("ck_agent_versions_instructions"), "agent_versions", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_agent_versions_instructions"),
        "agent_versions",
        "char_length(instructions) BETWEEN 1 AND 4000",
    )
    op.drop_constraint(op.f("ck_agent_versions_role"), "agent_versions", type_="check")
    op.drop_column("agent_versions", "role")
