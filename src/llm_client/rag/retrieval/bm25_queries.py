"""BM25 SQL query constants for PostgreSQL tsvector-based retrieval."""

# Standard BM25 search query using websearch_to_tsquery, scoped by user_id
BM25_SEARCH_SQL = """
SELECT
    id,
    content,
    metadata,
    ts_rank(search_vector, query) AS bm25_score,
    ts_headline($PG_TEXT_SEARCH_CONFIG, content, query,
      'StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=10,
      MaxFragments=3') AS snippet
FROM documents, websearch_to_tsquery($PG_TEXT_SEARCH_CONFIG, $1) AS query
WHERE search_vector @@ query
  AND user_id = $2
ORDER BY bm25_score DESC
LIMIT $3
"""

# Same query without user_id filter (dev / single-tenant retrieval)
BM25_SEARCH_ALL_USERS_SQL = """
SELECT
    id,
    content,
    metadata,
    ts_rank(search_vector, query) AS bm25_score,
    ts_headline($PG_TEXT_SEARCH_CONFIG, content, query,
      'StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=10,
      MaxFragments=3') AS snippet
FROM documents, websearch_to_tsquery($PG_TEXT_SEARCH_CONFIG, $1) AS query
WHERE search_vector @@ query
ORDER BY bm25_score DESC
LIMIT $2
"""

# BM25 search with fuzzy matching using pg_trgm similarity, scoped by user_id
BM25_SEARCH_WITH_FUZZY_SQL = """
SELECT
    d.id,
    d.content,
    d.metadata,
    ts_rank(d.search_vector, query) AS bm25_score,
    similarity($1, d.content) AS fuzzy_score,
    ts_headline($PG_TEXT_SEARCH_CONFIG, d.content, query,
      'StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=10,
      MaxFragments=3') AS snippet
FROM documents d, websearch_to_tsquery($PG_TEXT_SEARCH_CONFIG, $1) AS query
WHERE (d.search_vector @@ query OR similarity($1, d.content) > 0.05)
  AND d.user_id = $2
ORDER BY (ts_rank(d.search_vector, query) + similarity($1, d.content) * 0.3) DESC
LIMIT $3
"""

# Fuzzy search without user_id filter
BM25_SEARCH_WITH_FUZZY_ALL_USERS_SQL = """
SELECT
    d.id,
    d.content,
    d.metadata,
    ts_rank(d.search_vector, query) AS bm25_score,
    similarity($1, d.content) AS fuzzy_score,
    ts_headline($PG_TEXT_SEARCH_CONFIG, d.content, query,
      'StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=10,
      MaxFragments=3') AS snippet
FROM documents d, websearch_to_tsquery($PG_TEXT_SEARCH_CONFIG, $1) AS query
WHERE d.search_vector @@ query OR similarity($1, d.content) > 0.05
ORDER BY (ts_rank(d.search_vector, query) + similarity($1, d.content) * 0.3) DESC
LIMIT $2
"""
