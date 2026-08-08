"""create clauses table

Revision ID: f2e8d8b65a11
Revises: a7a9c4b2f1d0
Create Date: 2026-08-09 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2e8d8b65a11"
down_revision: str | Sequence[str] | None = "a7a9c4b2f1d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TYPE document_status
        ADD VALUE IF NOT EXISTS 'CLAUSES_SEGMENTED'
        """
    )
    op.create_table(
        "clauses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("clause_id", sa.String(length=80), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_start", sa.Integer(), nullable=False),
        sa.Column("source_end", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_clauses_clause_id"),
        "clauses",
        ["clause_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clauses_document_id"),
        "clauses",
        ["document_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_clauses_document_id_clause_id",
        "clauses",
        ["document_id", "clause_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_clauses_document_id_clause_id",
        "clauses",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_clauses_document_id"),
        table_name="clauses",
    )
    op.drop_index(
        op.f("ix_clauses_clause_id"),
        table_name="clauses",
    )
    op.drop_table("clauses")
