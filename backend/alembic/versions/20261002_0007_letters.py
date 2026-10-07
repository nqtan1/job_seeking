"""letters and letter_versions

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ck(name: str, expr: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(expr, name=op.f(f"ck_letters_{name}"))


def upgrade() -> None:
    op.create_table(
        "letters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(), server_default="cover", nullable=False),
        sa.Column("template", sa.String(), server_default="classic", nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latex_override", sa.Text(), nullable=True),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("tone", sa.String(), nullable=False),
        sa.Column("length", sa.String(), nullable=False),
        sa.Column("company_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column("render_status", sa.String(), server_default="none", nullable=False),
        sa.Column("pdf_document_id", sa.Uuid(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _ck("kind", "kind IN ('cover')"),
        _ck("template", "template IN ('classic', 'modern', 'compact', 'lettre_fr')"),
        _ck("language", "language IN ('fr', 'en')"),
        _ck(
            "tone",
            "tone IN ('professional', 'warm', 'confident', 'academic', 'formal')",
        ),
        _ck("length", "length IN ('short', 'standard', 'detailed')"),
        _ck("company_type", "company_type IN ('corporate', 'startup', 'phd')"),
        _ck("status", "status IN ('draft', 'final')"),
        _ck("render_status", "render_status IN ('none', 'queued', 'done', 'failed')"),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_letters_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_postings.id"],
            name=op.f("fk_letters_job_id_job_postings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["pdf_document_id"],
            ["documents.id"],
            name=op.f("fk_letters_pdf_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_letters")),
    )
    op.create_index("ix_letters_org_id_created_at", "letters", ["org_id", "created_at"])
    op.create_index("ix_letters_org_id_job_id", "letters", ["org_id", "job_id"])
    op.create_table(
        "letter_versions",
        sa.Column("letter_id", sa.Uuid(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["letter_id"],
            ["letters.id"],
            name=op.f("fk_letter_versions_letter_id_letters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_letter_versions_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("letter_id", "n", name=op.f("pk_letter_versions")),
    )
    op.create_index(
        "ix_letter_versions_org_id_created_at",
        "letter_versions",
        ["org_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("letter_versions")
    op.drop_table("letters")
