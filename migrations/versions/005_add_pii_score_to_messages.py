"""ADR-014 D-5: Add PII score and entities to messages table.

Revision ID: 005
Revises: 004
Create Date: 2026-09-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS pii_score FLOAT")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS pii_entities JSONB")
    op.create_index(
        "idx_messages_pii_score",
        "messages",
        ["pii_score"],
        postgresql_where="pii_score IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("idx_messages_pii_score", table_name="messages")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS pii_entities")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS pii_score")
