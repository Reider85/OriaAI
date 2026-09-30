"""Phase 2 A-3: Add tsvector column + GIN index for full-text search.

Revision ID: 007
Revises: 006
Create Date: 2026-09-26

Amended (D-2): search_vector is a real tsvector GENERATED ALWAYS AS STORED
column (auto-recomputed on content/metadata UPDATE). content_hash gains a
unique index so BM25IndexBuilder ON CONFLICT upsert works. GIN indexes are
created CONCURRENTLY outside the migration transaction.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

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

    op.drop_column("documents", "search_vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
