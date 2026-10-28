"""documents.kind accepts 'signature' (the user's handwritten signature PNG, ADR 0030)

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_documents_kind"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_kind"),
        "documents",
        "kind IN ('cv', 'jd', 'letter_pdf', 'attachment', 'export', 'signature')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM documents WHERE kind = 'signature'")
    op.drop_constraint(op.f("ck_documents_kind"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_kind"),
        "documents",
        "kind IN ('cv', 'jd', 'letter_pdf', 'attachment', 'export')",
    )
