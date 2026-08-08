"""create clause_classifications table

Revision ID: h1i2j3k4l5m6
Revises: f2e8d8b65a11
Create Date: 2026-08-09 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h1i2j3k4l5m6"
down_revision: str | Sequence[str] | None = "f2e8d8b65a11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TYPE document_status
        ADD VALUE IF NOT EXISTS 'CLASSIFIED'
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'clause_category'
            ) THEN
                CREATE TYPE clause_category AS ENUM (
                    'PAYMENT',
                    'TERMINATION',
                    'LIABILITY_LIMITATION',
                    'INDEMNIFICATION',
                    'CONFIDENTIALITY',
                    'DISPUTE_RESOLUTION',
                    'GOVERNING_LAW',
                    'FORCE_MAJEURE',
                    'INTELLECTUAL_PROPERTY',
                    'WARRANTY',
                    'ASSIGNMENT',
                    'DEFINITIONS',
                    'TERM_AND_RENEWAL',
                    'NOTICE',
                    'AMENDMENT',
                    'SEVERABILITY',
                    'ENTIRE_AGREEMENT',
                    'RECITALS',
                    'OTHER'
                );
            END IF;
        END
        $$;
        """
    )
    op.create_table(
        "clause_classifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("clause_pk", sa.String(length=36), nullable=False),
        sa.Column("clause_id", sa.String(length=80), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "PAYMENT",
                "TERMINATION",
                "LIABILITY_LIMITATION",
                "INDEMNIFICATION",
                "CONFIDENTIALITY",
                "DISPUTE_RESOLUTION",
                "GOVERNING_LAW",
                "FORCE_MAJEURE",
                "INTELLECTUAL_PROPERTY",
                "WARRANTY",
                "ASSIGNMENT",
                "DEFINITIONS",
                "TERM_AND_RENEWAL",
                "NOTICE",
                "AMENDMENT",
                "SEVERABILITY",
                "ENTIRE_AGREEMENT",
                "RECITALS",
                "OTHER",
                name="clause_category",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("raw_response", sa.JSON(), nullable=False),
        sa.Column("source_start", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_end", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["clause_pk"],
            ["clauses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_clause_classifications_document_id"),
        "clause_classifications",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clause_classifications_clause_pk"),
        "clause_classifications",
        ["clause_pk"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clause_classifications_clause_id"),
        "clause_classifications",
        ["clause_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_clause_classifications_document_clause",
        "clause_classifications",
        ["document_id", "clause_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_clause_classifications_document_clause",
        "clause_classifications",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_clause_classifications_clause_id"),
        table_name="clause_classifications",
    )
    op.drop_index(
        op.f("ix_clause_classifications_clause_pk"),
        table_name="clause_classifications",
    )
    op.drop_index(
        op.f("ix_clause_classifications_document_id"),
        table_name="clause_classifications",
    )
    op.drop_table("clause_classifications")
