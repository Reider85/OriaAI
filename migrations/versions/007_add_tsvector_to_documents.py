"""Phase 2 A-3: Add tsvector column + GIN index for full-text search.

Revision ID: 007
Revises: 006
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pg_trgm extension for fuzzy matching
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    
    # Add tsvector column (computed from content + metadata.title)
    op.add_column(
        "documents",
        sa.Column(
            "search_vector",
            sa.Text(),
            nullable=False,
            server_default=sa.text(
                "setweight(to_tsvector('english', coalesce(content, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(metadata->>'title', '')), 'B')"
            )
        )
    )
    
    # Create GIN index for fast tsvector queries
    op.create_index(
        "idx_documents_search_vector",
        "documents",
        ["search_vector"],
        postgresql_using="gin"
    )
    
    # Create trigram index for fuzzy matching (optional, for Russian terms)
    op.create_index(
        "idx_documents_content_trgm",
        "documents",
        ["content"],
        postgresql_using="gin",
        postgresql_ops={"content": "gin_trgm_ops"}
    )
    
    # Add tsvector_length for ranking
    op.create_index(
        "idx_documents_ts_rank",
        "documents",
        [sa.text("ts_rank(search_vector, websearch_to_tsquery('english', ''))")],
        postgresql_where=sa.text("search_vector IS NOT NULL")
    )


def downgrade() -> None:
    op.drop_index("idx_documents_ts_rank", table_name="documents")
    op.drop_index("idx_documents_content_trgm", table_name="documents")
    op.drop_index("idx_documents_search_vector", table_name="documents")
    op.drop_column("documents", "search_vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")