"""Phase 3 A-3: Create documents_facts table for Tier-1 facts cache.

Revision ID: 009
Revises: 008
Create Date: 2026-10-19

Implements: ADR-011 Tier-1 storage for facts extraction (Phase 3 — Beta).
Architecture: ARCHITECT.md v1.3.0 §5.2.5, §5.2.7 (Persistence).
TRIZ: Standard 1.1.5 (введение второго поля в веполь), principle
#17 (переход в другое измерение — extraction на индекс-тайм).
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Ensure pgvector extension is available
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create documents_facts table
    op.create_table(
        "documents_facts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("fact_text", sa.Text, nullable=False),
        sa.Column(
            "fact_embedding",
            Vector(1536),  # pgvector type; dimension 1536 = text-embedding-3-small (Phase 3 default)
            nullable=True,  # nullable: facts can be extracted without embedding first
        ),
        sa.Column(
            "fact_metadata",
            postgresql.JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "extractor_model",
            sa.String(100),
            nullable=True,  # e.g. "gpt-4o-mini" or "ollama/llama3.1"
        ),
    )

    # 3. Indexes
    op.create_index(
        "ix_documents_facts_document_id",
        "documents_facts",
        ["document_id"],
    )
    op.create_index(
        "ix_documents_facts_extracted_at",
        "documents_facts",
        ["extracted_at"],
    )

    # 4. HNSW index on fact_embedding for fast cosine sim
    # NOTE: pgvector >=0.5.0 required; check pgvector version in CI.
    op.execute(
        "CREATE INDEX ix_documents_facts_embedding_hnsw "
        "ON documents_facts USING hnsw (fact_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )

    # 5. GIN index for full-text search on facts (antipattern requirement)
    op.execute(
        "CREATE INDEX ix_documents_facts_text_search "
        "ON documents_facts USING GIN (to_tsvector('english', fact_text))"
    )


def downgrade() -> None:
    op.drop_index("ix_documents_facts_embedding_hnsw", table_name="documents_facts")
    op.drop_index("ix_documents_facts_text_search", table_name="documents_facts")
    op.drop_index("ix_documents_facts_extracted_at", table_name="documents_facts")
    op.drop_index("ix_documents_facts_document_id", table_name="documents_facts")
    op.drop_table("documents_facts")
    # NOTE: do NOT drop pgvector extension (may be used by other tables)