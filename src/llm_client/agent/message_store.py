"""Message persistence for chat history with PII metadata (ADR-014 D-5).

Provides storage for user/assistant/tool messages in the messages table,
with PII metadata for user messages and proper UUID mapping for session/user IDs.
"""
import uuid
from typing import Any

import asyncpg
from pydantic import BaseModel

from ..security.pii_detector import PIIDetectionResult

# Fixed namespace for deterministic UUID mapping
# Namespace derived from "llm-client-chat" UUIDv5 for stable mapping
NAMESPACE = uuid.UUID("6c2e8e5e-2a4f-4a6b-8c4e-4f6a8c4e4f6a")


class MessageContent(BaseModel):
    """Content model for messages table JSONB column."""
    text: str


class ToolMessageContent(BaseModel):
    """Content model for tool messages."""
    tool_call_id: str
    tool_name: str
    text: str


def map_string_id(s: str) -> uuid.UUID:
    """Map string ID to deterministic UUID using namespace.
    
    Ensures stable mapping of user_id/session_id from API (strings) to DB (UUID).
    """
    return uuid.uuid5(NAMESPACE, s)


async def ensure_chat_parents(
    pool: asyncpg.Pool,
    user_key: str,
    session_key: str,
    provider: str,
    model_name: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Ensure users and sessions exist, return UUIDs.
    
    Args:
        pool: PostgreSQL connection pool
        user_key: string user_id from API
        session_key: string session_id from API
        provider: LLM provider (e.g., "openai")
        model_name: model name (e.g., "gpt-4-turbo")
        
    Returns:
        Tuple of (user_uuid, session_uuid)
    """
    user_uuid = map_string_id(user_key)
    session_uuid = map_string_id(session_key)
    
    async with pool.acquire() as conn:
        # Ensure user exists
        await conn.execute(
            "INSERT INTO users (id) VALUES ($1) ON CONFLICT DO NOTHING",
            user_uuid,
        )
        
        # Ensure session exists
        await conn.execute(
            """
            INSERT INTO sessions (id, user_id, provider, model_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE SET
                updated_at = now(),
                provider = excluded.provider,
                model_name = excluded.model_name
            """,
            session_uuid,
            user_uuid,
            provider,
            model_name,
        )
    
    return user_uuid, session_uuid


async def insert_message(
    pool: asyncpg.Pool,
    *,
    message_id: uuid.UUID,
    session_id: uuid.UUID,
    role: str,
    content: dict[str, Any],
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
    pii_score: float | None = None,
    pii_entities: list[dict] | None = None,
) -> None:
    """Insert a message into the messages table.
    
    Args:
        pool: PostgreSQL connection pool
        message_id: UUID of the message
        session_id: UUID of the session (FK)
        role: "user", "assistant", or "tool"
        content: JSONB content dict
        tokens_in: Optional input token count
        tokens_out: Optional output token count
        cost_usd: Optional cost in USD
        pii_score: Optional PII score (0-1)
        pii_entities: Optional list of entity dicts (type, start, end)
    """
    if pool is None:
        # Graceful degradation when pool unavailable (e.g., no DB)
        return
    
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO messages (
                id, session_id, role, content,
                tokens_in, tokens_out, cost_usd,
                pii_score, pii_entities
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            message_id,
            session_id,
            role,
            content,
            tokens_in,
            tokens_out,
            cost_usd,
            pii_score,
            pii_entities,
        )


def detection_to_columns(
    detection: PIIDetectionResult,
    enabled: bool,
) -> tuple[float | None, list[dict] | None]:
    """Convert PIIDetectionResult to DB columns.
    
    Args:
        detection: PII detection result
        enabled: Whether PII metadata is enabled
        
    Returns:
        Tuple of (pii_score, pii_entities)
    """
    if not enabled:
        return None, None
    
    # Convert entities to DB format (type, start, end only)
    entities = [
        {"type": e.type, "start": e.start, "end": e.end}
        for e in detection.entities
    ]
    
    return detection.score, entities


__all__ = [
    "MessageContent",
    "ToolMessageContent",
    "detection_to_columns",
    "ensure_chat_parents",
    "insert_message",
    "map_string_id",
]