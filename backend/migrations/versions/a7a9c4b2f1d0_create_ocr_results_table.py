"""create ocr results table

Revision ID: a7a9c4b2f1d0
Revises: d5f381a3b7e2
Create Date: 2026-08-08 22:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7a9c4b2f1d0"
down_revision: str | Sequence[str] | None = "d5f381a3b7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ocr_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
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
        op.f("ix_ocr_results_document_id"),
        "ocr_results",
        ["document_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ocr_results_document_id"),
        table_name="ocr_results",
    )
    op.drop_table("ocr_results")
