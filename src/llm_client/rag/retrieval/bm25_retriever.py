"""BM25Retriever for PostgreSQL tsvector-based document retrieval."""

import logging
from typing import Any

import asyncpg

from .bm25_queries import BM25_SEARCH_SQL, BM25_SEARCH_WITH_FUZZY_SQL

logger = logging.getLogger(__name__)


class BM25Retriever:
    """Retriever for BM25 search using PostgreSQL tsvector.

    Implements PostgreSQL full-text search with tsvector and optional
    fuzzy matching via pg_trgm. Returns documents ranked by BM25 score
    with highlighted snippets.
    """

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        text_search_config: str = "english",
        fuzzy_enabled: bool = False,
    ):
        """Initialize BM25Retriever.

        Args:
            pg_pool: asyncpg connection pool for PostgreSQL
            text_search_config: PostgreSQL text search configuration
                (e.g., "english", "russian")
            fuzzy_enabled: Enable pg_trgm fuzzy matching for approximate searches
        """
        self._pool = pg_pool
        self._text_search_config = text_search_config
        self._fuzzy_enabled = fuzzy_enabled

    async def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve documents using BM25 search.

        Args:
            query: Search query string
            user_id: User ID for multi-tenancy filtering
            top_k: Maximum number of documents to return

        Returns:
            List of document dictionaries with keys:
                - id: Document UUID
                - content: Document content
                - metadata: Document metadata JSON
                - score: BM25 relevance score
                - snippet: Highlighted content excerpt

        Raises:
            asyncpg.PostgresError: If database operation fails
        """
        if not query.strip():
            logger.warning("Empty query provided to BM25Retriever")
            return []

        # Select appropriate SQL based on fuzzy matching
        sql = BM25_SEARCH_WITH_FUZZY_SQL if self._fuzzy_enabled else BM25_SEARCH_SQL

        # Replace PG_TEXT_SEARCH_CONFIG placeholder with actual config
        # This is cleaner than using parameter interpolation for config
        sql = sql.replace("$PG_TEXT_SEARCH_CONFIG", f"'{self._text_search_config}'")

        try:
            async with self._pool.acquire() as conn:
                # Set search configuration for this connection
                await conn.execute(f"SET search_config = '{self._text_search_config}'")

                # Execute query with parameters
                rows = await conn.fetch(sql, query, user_id, top_k)

                # Convert rows to result format
                results = []
                for row in rows:
                    result = {
                        "id": str(row["id"]),
                        "content": row["content"],
                        "metadata": row["metadata"],
                        "score": float(row["bm25_score"]),
                        "snippet": row["snippet"],
                    }
                    results.append(result)

                logger.debug(
                    "BM25Retriever retrieved %d documents for query: %s", len(results), query
                )
                return results

        except asyncpg.PostgresError as e:
            logger.error("BM25 search failed for query='%s', error=%s", query, str(e))
            raise
        except Exception as e:
            logger.error("Unexpected error in BM25Retriever for query='%s': %s", query, str(e))
            raise
