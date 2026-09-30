"""Baseline Phase 1 schema for fresh databases.

Revision ID: 004
Revises: None
Create Date: 2026-09-30

Creates the base tables that migration 005 (messages PII columns) and the
rest of the Alembic chain assume already exist. On databases where Phase 1
tables were created outside Alembic, stamp past this revision.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = None
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
        CREATE TABLE IF NOT EXISTS sessions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT,
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id UUID PRIMARY KEY,
            session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content JSONB NOT NULL,
            tokens_in INT,
            tokens_out INT,
            cost_usd NUMERIC(10,6),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id UUID PRIMARY KEY,
            session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id),
            path TEXT NOT NULL,
            format TEXT NOT NULL,
            size_bytes BIGINT NOT NULL,
            sha256 TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_calls (
            id UUID PRIMARY KEY,
            session_id UUID REFERENCES sessions(id),
            message_id UUID REFERENCES messages(id),
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            tokens_in INT,
            tokens_out INT,
            latency_ms INT,
            cost_usd NUMERIC(10,6),
            status TEXT NOT NULL,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_checkpoints (
            thread_id UUID NOT NULL,
            checkpoint_id UUID NOT NULL,
            parent_id UUID,
            state JSONB NOT NULL,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (thread_id, checkpoint_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_checkpoints")
    op.execute("DROP TABLE IF EXISTS llm_calls")
    op.execute("DROP TABLE IF EXISTS files")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS users")
