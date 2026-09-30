"""Phase 2 A-3: Create documents table for RAG full-text search.

Revision ID: 006
Revises: 005
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            source_uri TEXT,
            content_hash TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents (source_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents (content_hash)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS documents")
