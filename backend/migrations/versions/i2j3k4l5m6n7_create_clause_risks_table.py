from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "i2j3k4l5m6n7"
down_revision: str | Sequence[str] | None = "h1i2j3k4l5m6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'RISK_SCORED' AFTER 'CLASSIFIED'"
    )

    risk_level_enum = postgresql.ENUM(
        "LOW", "MEDIUM", "HIGH", name="risk_level", create_type=False
    )
    risk_level_enum.create(op.get_bind(), checkfirst=True)

    risk_flag_type_enum = postgresql.ENUM(
        "UNFAIR_TERM",
        "ONE_SIDED",
        "AMBIGUOUS",
        "FAIR",
        name="risk_flag_type",
        create_type=False,
    )
    risk_flag_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "clause_risks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("clause_id", sa.String(), nullable=False),
        sa.Column("clause_pk", sa.String(), nullable=False),
        sa.Column("risk_level", sa.Enum("LOW", "MEDIUM", "HIGH", name="risk_level"), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_reason", sa.Text(), nullable=False),
        sa.Column(
            "flag_type",
            sa.Enum("UNFAIR_TERM", "ONE_SIDED", "AMBIGUOUS", "FAIR", name="risk_flag_type"),
            nullable=False,
        ),
        sa.Column("suggested_mitigation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clause_pk"], ["clauses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clause_risks_document_id"), "clause_risks", ["document_id"], unique=False)
    op.create_index(op.f("ix_clause_risks_clause_id"), "clause_risks", ["clause_id"], unique=False)
    op.create_index(op.f("ix_clause_risks_clause_pk"), "clause_risks", ["clause_pk"], unique=False)
    op.create_index(op.f("ix_clause_risks_risk_level"), "clause_risks", ["risk_level"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_clause_risks_risk_level"), table_name="clause_risks")
    op.drop_index(op.f("ix_clause_risks_clause_pk"), table_name="clause_risks")
    op.drop_index(op.f("ix_clause_risks_clause_id"), table_name="clause_risks")
    op.drop_index(op.f("ix_clause_risks_document_id"), table_name="clause_risks")
    op.drop_table("clause_risks")

    risk_flag_type_enum = postgresql.ENUM(name="risk_flag_type")
    risk_flag_type_enum.drop(op.get_bind(), checkfirst=True)

    risk_level_enum = postgresql.ENUM(name="risk_level")
    risk_level_enum.drop(op.get_bind(), checkfirst=True)
