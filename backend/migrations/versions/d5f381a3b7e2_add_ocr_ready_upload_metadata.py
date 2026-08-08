"""add ocr ready upload metadata

Revision ID: d5f381a3b7e2
Revises: c3f0c82d3540
Create Date: 2026-08-08 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5f381a3b7e2"
down_revision: str | Sequence[str] | None = "c3f0c82d3540"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("object_key", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "checksum_algorithm",
            sa.String(length=20),
            server_default="SHA-256",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE documents
        SET object_key = regexp_replace(storage_uri, '^s3://[^/]+/', '')
        WHERE object_key IS NULL
        """
    )
    op.alter_column("documents", "object_key", nullable=False)
    op.create_index(
        op.f("ix_documents_object_key"),
        "documents",
        ["object_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_documents_object_key"),
        table_name="documents",
    )
    op.drop_column("documents", "checksum_algorithm")
    op.drop_column("documents", "object_key")
