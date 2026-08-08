"""add document hash constraint

Revision ID: c3f0c82d3540
Revises: 37b909f99365
Create Date: 2026-08-08 20:27:59.089488

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f0c82d3540'
down_revision: str | Sequence[str] | None = '37b909f99365'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('documents', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'documentstatus'
            )
            AND NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'document_status'
            ) THEN
                ALTER TYPE documentstatus RENAME TO document_status;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'document_status'
            )
            AND NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'documentstatus'
            ) THEN
                ALTER TYPE document_status RENAME TO documentstatus;
            END IF;
        END $$;
        """
    )
    op.drop_column('documents', 'updated_at')
    op.drop_column('documents', 'created_at')
