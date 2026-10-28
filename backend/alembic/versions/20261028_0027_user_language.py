"""users.language (en/fr/vi) and Vietnamese letters

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("language", sa.String(2), nullable=False, server_default="en"),
    )
    op.create_check_constraint(
        op.f("ck_users_language"), "users", "language IN ('en', 'fr', 'vi')"
    )
    op.drop_constraint(op.f("ck_letters_language"), "letters", type_="check")
    op.create_check_constraint(
        op.f("ck_letters_language"), "letters", "language IN ('fr', 'en', 'vi')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_letters_language"), "letters", type_="check")
    op.create_check_constraint(
        op.f("ck_letters_language"), "letters", "language IN ('fr', 'en')"
    )
    op.drop_constraint(op.f("ck_users_language"), "users", type_="check")
    op.drop_column("users", "language")
