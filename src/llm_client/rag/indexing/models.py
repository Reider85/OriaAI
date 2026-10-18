"""Document and Chunk ORM models for BM25 indexing and facts extraction.

Phase 3 A-3: Convert from dataclasses to SQLAlchemy declarative models.
- Document: maps to documents table (id, user_id, source_type, source_uri, content_hash, content, metadata)
- DocumentFact: maps to documents_facts table (id, document_id, fact_text, fact_embedding, fact_metadata, extracted_at, extractor_model)
- Chunk: remains dataclass (not used as ORM entity)
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import ForeignKey, event
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime, String, Text

# pgvector Vector type will be imported where used (avoiding circular import)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Document(Base):
    """ORM model for documents table.

    Phase 3 A-3: Converted from dataclass to declarative ORM.
    Preserves content_hash auto-computation via custom __init__.
    """

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Phase 3 A-3: Relationship to facts
    facts: Mapped[list["DocumentFact"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    def __init__(
        self,
        user_id: str,
        source_type: str,
        id: str | None = None,
        source_uri: str | None = None,
        content_hash: str | None = None,
        content: str = "",
        meta: dict[str, Any] | None = None,
    ):
        """Initialize Document with auto content_hash computation.

        Preserves dataclass behavior: if content_hash not provided, compute it.
        """
        if id is None:
            self.id = uuid4()
        else:
            self.id = UUID(id)

        self.user_id = user_id
        self.source_type = source_type
        self.source_uri = source_uri
        self.content = content
        self.meta = meta or {}

        # Auto-compute content_hash if not provided (dataclass behavior)
        if content_hash:
            self.content_hash = content_hash
        else:
            self.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


class DocumentFact(Base):
    """ORM model for documents_facts table (Phase 3 A-3 Tier-1 facts cache)."""

    __tablename__ = "documents_facts"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    document_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    fact_embedding: Mapped[list[float] | None] = mapped_column(
        "fact_embedding", JSONB, nullable=True  # TODO: Use pgvector.Vector when available
    )
    fact_metadata: Mapped[dict] = mapped_column(
        "fact_metadata", JSONB, server_default="{}", nullable=False
    )
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    extractor_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationship to parent document
    document: Mapped[Document] = relationship(back_populates="facts")


@event.listens_for(Document, "before_insert")
@event.listens_for(Document, "before_update")
def normalize_metadata(mapper, connection, target):
    """Ensure metadata is never None (convert empty dict to JSONB '{}')."""
    if target.metadata is None:
        target.metadata = {}


# Keep Chunk as dataclass (not used as ORM entity)
@dataclass
class Chunk:
    """A single chunk of a parent document for vector-side indexing.

    BM25 indexes the concatenated parent content (see
    ``BM25IndexBuilder.index_chunks``); the vector store may persist chunks
    individually with metadata pointing back at the parent document.

    Phase 3 A-3: Remains dataclass (not used as ORM entity).
    """

    document_id: str
    user_id: str
    source_type: str
    content: str
    chunk_index: int = 0
    source_uri: str | None = None
    content_hash: str = ""
    meta: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.meta is None:
            self.meta = {}