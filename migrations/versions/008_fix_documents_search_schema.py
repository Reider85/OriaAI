"""Phase 2 D-2: Corrective migration for databases that applied broken 007.

Revision ID: 008
Revises: 007
Create Date: 2026-09-30

Broken 007 typed search_vector as Text() with server_default instead of
tsvector GENERATED ALWAYS AS STORED, and left content_hash non-unique.
This migration detects the current column type and repairs it in place.
Fresh databases that ran the amended 007 are a no-op for the column rebuild.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    col_type = op.get_bind().execute(
        sa.text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'documents' AND column_name = 'search_vector'
            """
        )
    ).scalar()

    needs_rebuild = col_type is None or col_type != "tsvector"

    if needs_rebuild:
        op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_vector;")
        op.execute(
            """
            ALTER TABLE documents
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(content, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(metadata->>'title', '')), 'B')
            ) STORED
            """
        )

    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
                idx_documents_content_hash_unique ON documents (content_hash)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_documents_search_vector ON documents USING GIN (search_vector)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_documents_content_trgm ON documents USING GIN (content gin_trgm_ops)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_documents_content_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_documents_search_vector")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_documents_content_hash_unique")

    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_vector;")
