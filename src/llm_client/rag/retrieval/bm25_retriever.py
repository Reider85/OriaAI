"""BM25Retriever for PostgreSQL tsvector-based document retrieval."""

import logging
from typing import Any

import asyncpg

from .bm25_queries import (
    BM25_SEARCH_ALL_USERS_SQL,
    BM25_SEARCH_SQL,
    BM25_SEARCH_WITH_FUZZY_ALL_USERS_SQL,
    BM25_SEARCH_WITH_FUZZY_SQL,
)

logger = logging.getLogger(__name__)


class RetrievalError(Exception):
    """Raised when a retrieval leg fails or is not wired."""


class BM25Retriever:
    """Retriever for BM25 search using PostgreSQL tsvector.

    Implements PostgreSQL full-text search with tsvector and optional
    fuzzy matching via pg_trgm. Returns documents ranked by BM25 score
    with highlighted snippets.
    """

    def __init__(
        self,
        pg_pool: asyncpg.Pool | None,
        text_search_config: str = "english",
        fuzzy_enabled: bool = False,
    ):
        """Initialize BM25Retriever.

        Args:
            pg_pool: asyncpg connection pool for PostgreSQL. None means the
                retriever is not wired — ``retrieve``/``aretrieve`` raise
                RetrievalError instead of crashing with AttributeError.
            text_search_config: PostgreSQL text search configuration
                (e.g., "english", "russian")
            fuzzy_enabled: Enable pg_trgm fuzzy matching for approximate searches
        """
        self._pool = pg_pool
        self._text_search_config = text_search_config
        self._fuzzy_enabled = fuzzy_enabled

    @property
    def pg_pool(self) -> asyncpg.Pool | None:
        return self._pool

    async def aretrieve(
        self,
        query: str,
        user_id: str = "",
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Async retrieval entry point (duck-typed match for RagPipeline)."""
        return await self.retrieve(query, user_id=user_id, top_k=top_k)

    async def retrieve(
        self,
        query: str,
        user_id: str = "",
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve documents using BM25 search.

        Args:
            query: Search query string
            user_id: Optional user ID for multi-tenancy filtering. Empty
                string retrieves across all users (dev-friendly default).
            top_k: Maximum number of documents to return

        Returns:
            List of document dictionaries with keys:
                - id: Document UUID
                - content: Document content
                - metadata: Document metadata JSON
                - score: BM25 relevance score
                - snippet: Highlighted content excerpt

        Raises:
            RetrievalError: If pg_pool is not wired
            asyncpg.PostgresError: If database operation fails
        """
        if not query.strip():
            logger.warning("Empty query provided to BM25Retriever")
            return []

        if self._pool is None:
            raise RetrievalError(
                "BM25Retriever has no pg_pool — wire the shared pool via "
                "RagPipeline.from_settings / agent-service startup"
            )

        scoped = bool(user_id and user_id != "anonymous")
        if self._fuzzy_enabled:
            sql = BM25_SEARCH_WITH_FUZZY_SQL if scoped else BM25_SEARCH_WITH_FUZZY_ALL_USERS_SQL
        else:
            sql = BM25_SEARCH_SQL if scoped else BM25_SEARCH_ALL_USERS_SQL

        sql = sql.replace("$PG_TEXT_SEARCH_CONFIG", f"'{self._text_search_config}'")

        try:
            async with self._pool.acquire() as conn:
                if scoped:
                    rows = await conn.fetch(sql, query, user_id, top_k)
                else:
                    rows = await conn.fetch(sql, query, top_k)

                results = []
                for row in rows:
                    results.append(
                        {
                            "id": str(row["id"]),
                            "content": row["content"],
                            "metadata": row["metadata"],
                            "score": float(row["bm25_score"]),
                            "snippet": row["snippet"],
                        }
                    )

                logger.debug(
                    "BM25Retriever retrieved %d documents for query: %s",
                    len(results),
                    query,
                )
                return results

        except asyncpg.PostgresError as e:
            logger.error("BM25 search failed for query='%s', error=%s", query, str(e))
            raise
        except RetrievalError:
            raise
        except Exception as e:
            logger.error("Unexpected error in BM25Retriever for query='%s': %s", query, str(e))
            raise
