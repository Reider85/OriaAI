"""Phase 2 A-3: Create documents table for RAG full-text search.

Revision ID: 006
Revises: 005
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table first (foreign key dependency)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMPTZ(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Create documents table for RAG full-text search
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),  # Full text for search
        sa.Column("metadata", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.TIMESTAMPTZ(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users(id)"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Create indexes for performance
    op.create_index("idx_documents_user_id", "documents", ["user_id"])
    op.create_index("idx_documents_source_type", "documents", ["source_type"])
    op.create_index("idx_documents_content_hash", "documents", ["content_hash"])


def downgrade() -> None:
    op.drop_index("idx_documents_content_hash", table_name="documents")
    op.drop_index("idx_documents_source_type", table_name="documents")
    op.drop_index("idx_documents_user_id", table_name="documents")
    op.drop_table("documents")
    op.drop_table("users")