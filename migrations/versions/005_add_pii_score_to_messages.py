"""ADR-014 D-5: Add PII score and entities to messages table.

Revision ID: 005
Revises: None
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("pii_score", sa.Float, nullable=True))
    op.add_column("messages", sa.Column("pii_entities", postgresql.JSONB, nullable=True))
    op.create_index(
        "idx_messages_pii_score",
        "messages",
        ["pii_score"],
        postgresql_where="pii_score IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("idx_messages_pii_score", table_name="messages")
    op.drop_column("messages", "pii_entities")
    op.drop_column("messages", "pii_score")
