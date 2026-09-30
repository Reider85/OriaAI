"""Document and Chunk dataclasses for BM25 indexing."""

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass
class Document:
    """Document dataclass representing a record in the PostgreSQL documents table.

    This maps to the documents table schema from migration 006. Note that:
    - `created_at` is PostgreSQL-generated (DEFAULT now())
    - `search_vector` is PostgreSQL-generated (GENERATED ALWAYS AS STORED)

    Attributes:
        id: UUID string (primary key)
        user_id: UUID string (foreign key to users.id)
        source_type: String (e.g., "file", "url", "api")
        source_uri: Optional string (URL or file path)
        content_hash: SHA-256 hash of content (for deduplication)
        content: Full text content for search and retrieval
        metadata: JSONB dictionary for additional metadata
    """

    id: str
    user_id: str
    source_type: str
    source_uri: str | None = None
    content_hash: str = ""
    content: str = ""
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass
class Chunk:
    """A single chunk of a parent document for vector-side indexing.

    BM25 indexes the concatenated parent content (see
    ``BM25IndexBuilder.index_chunks``); the vector store may persist chunks
    individually with metadata pointing back at the parent document.
    """

    document_id: str
    user_id: str
    source_type: str
    content: str
    chunk_index: int = 0
    source_uri: str | None = None
    content_hash: str = ""
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}
