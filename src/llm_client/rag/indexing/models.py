"""Document dataclass for BM25 indexing."""

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
        """Ensure metadata is initialized as empty dict if None."""
        if self.metadata is None:
            self.metadata = {}