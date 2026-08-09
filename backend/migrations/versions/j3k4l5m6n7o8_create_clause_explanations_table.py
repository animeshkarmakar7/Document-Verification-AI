from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j3k4l5m6n7o8"
down_revision: str | Sequence[str] | None = "i2j3k4l5m6n7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'document_status' AND e.enumlabel = 'RISK_SCORED'
            ) THEN
                ALTER TYPE document_status ADD VALUE 'RISK_SCORED' AFTER 'CLASSIFIED';
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'document_status' AND e.enumlabel = 'EXPLAINED'
            ) THEN
                ALTER TYPE document_status ADD VALUE 'EXPLAINED' AFTER 'RISK_SCORED';
            END IF;
        END $$;
        """
    )

    op.create_table(
        "clause_explanations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("clause_id", sa.String(), nullable=False),
        sa.Column("clause_pk", sa.String(), nullable=False),
        sa.Column("plain_summary", sa.Text(), nullable=False),
        sa.Column("source_span_start", sa.Integer(), nullable=False),
        sa.Column("source_span_end", sa.Integer(), nullable=False),
        sa.Column("readability_score_original", sa.Float(), nullable=True),
        sa.Column("readability_score_summary", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_grounded", sa.Boolean(), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clause_pk"], ["clauses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_clause_explanations_document_id"),
        "clause_explanations",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clause_explanations_clause_id"),
        "clause_explanations",
        ["clause_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clause_explanations_clause_pk"),
        "clause_explanations",
        ["clause_pk"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_clause_explanations_clause_pk"), table_name="clause_explanations")
    op.drop_index(op.f("ix_clause_explanations_clause_id"), table_name="clause_explanations")
    op.drop_index(op.f("ix_clause_explanations_document_id"), table_name="clause_explanations")
    op.drop_table("clause_explanations")
