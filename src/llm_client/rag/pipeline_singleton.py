"""Shared RAG pipeline singleton for rag_query tool (ADR-003, Phase 2).

Implements singleton pattern to avoid recreating RagPipeline on every tool call,
which causes significant performance overhead with vector stores like Chroma.
"""

import logging
from contextvars import ContextVar, Token
from typing import Any

from llm_client.config import Settings

logger = logging.getLogger(__name__)

# Context for passing request-level overrides to tools
_rag_request_overrides: ContextVar[dict | None] = ContextVar("rag_request_overrides", default=None)

_pipeline: Any = None
_pipeline_settings: Settings | None = None
_override_cache: dict[tuple, Any] = {}


async def get_shared_pipeline(settings: Settings | None = None) -> Any:
    """Return the process-wide RagPipeline, creating it on first use.

    The caller does NOT own the pipeline — close it via ``close_shared_pipeline()``
    during application shutdown.
    """
    global _pipeline, _pipeline_settings

    if _pipeline is not None:
        return _pipeline

    if settings is None:
        from llm_client.config import settings as default_settings

        settings = default_settings

    try:
        from .pipeline import RagPipeline

        # Use shared pool if available, otherwise create one
        from .pool import get_shared_pool

        pg_pool = await get_shared_pool(settings)

        _pipeline = RagPipeline.from_settings(settings, pg_pool=pg_pool)
        _pipeline_settings = settings
        logger.info(
            "Shared RagPipeline created for vector store: %s", settings.vector_store_kind or "none"
        )
        return _pipeline
    except (ImportError, ValueError, RuntimeError) as exc:
        logger.warning("Failed to create shared RagPipeline: %s", exc)
        # Return a minimal pipeline that will handle gracefully
        _pipeline = _create_fallback_pipeline()
        _pipeline_settings = settings
        return _pipeline


def get_shared_pipeline_sync() -> Any | None:
    """Return the shared pipeline if it already exists, else None."""
    return _pipeline


def set_rag_request_overrides(overrides: dict | None) -> Token:
    """Set request-level RAG overrides for tools. Returns token for reset."""
    return _rag_request_overrides.set(overrides)


def get_rag_request_overrides() -> dict | None:
    """Get current request-level RAG overrides for tools."""
    return _rag_request_overrides.get()


def reset_rag_request_overrides(token: Token | None) -> None:
    """Reset contextvar to its previous state using the token."""
    if token is not None:
        _rag_request_overrides.reset(token)


def _pipeline_cache_key(config: Any) -> tuple:
    """Generate a cache key from RetrieverConfig for override-based caching.

    Args:
        config: RetrieverConfig or object with relevant attributes

    Returns:
        Tuple of (retrieval_strategy, reranker_name, reranker_top_k, reranker_enabled)
    """
    # Handle both RetrieverConfig objects and any config-like object
    strategy = getattr(config, "retrieval_strategy", None)
    if strategy is not None and hasattr(strategy, "value"):
        strategy = strategy.value  # Convert enum to string

    return (
        strategy,
        getattr(config, "reranker_name", "bge"),
        getattr(config, "reranker_top_k", 5),
        getattr(config, "reranker_enabled", True),
    )


async def get_pipeline_for_request(
    app_settings: Settings | None = None,
    request_settings: dict | None = None,
    pg_pool: Any = None,
) -> Any:
    """Get a RagPipeline for a request, using tiered caching to avoid rebuilds.

    Tiered lookup:
    1. No overrides + startup singleton exists → return singleton (common case)
    2. Override key exists in cache → return cached
    3. Build new pipeline with overrides, cache it, return

    Args:
        app_settings: App settings for pg_pool lookup and config baseline
        request_settings: G-4 UI settings dict (retrieval_strategy, reranker, top_k)
        pg_pool: Optional explicit pg_pool (for graph node)

    Returns:
        RagPipeline instance or fallback pipeline
    """
    global _pipeline, _pipeline_settings, _override_cache  # noqa: PLW0602

    # Get baseline settings
    if app_settings is None:
        from llm_client.config import settings as default_settings

        app_settings = default_settings

    # Build config from env with overrides applied
    from .config import RetrieverConfig
    from .pipeline import _apply_retriever_overrides

    env_config = RetrieverConfig.from_env()
    config = _apply_retriever_overrides(env_config, request_settings)

    # Generate cache key
    key = _pipeline_cache_key(config)

    # Tier 1: No overrides + startup singleton exists (common case)
    env_key = _pipeline_cache_key(env_config)
    if key == env_key and _pipeline is not None:
        logger.debug("Request with no overrides → using startup singleton")
        return _pipeline

    # Tier 2: Check override cache
    if key in _override_cache:
        logger.debug("Override cache hit for key %s", key)
        return _override_cache[key]

        # Tier 3: Build new pipeline with overrides
        strategy = (
            config.retrieval_strategy.value
            if hasattr(config.retrieval_strategy, "value")
            else config.retrieval_strategy
        )
        logger.info(
            "Building new pipeline for overrides: %s (strategy=%s, reranker=%s, top_k=%s)",
            key,
            strategy,
            config.reranker_name,
            config.reranker_top_k,
        )

    try:
        # Use shared pool if pg_pool not provided
        if pg_pool is None:
            from .pool import resolve_pool

            pg_pool = resolve_pool(app_settings)

        from .pipeline import RagPipeline

        # Build pipeline with the overridden config
        pipeline = RagPipeline(
            retriever=_build_retriever(config, pg_pool=pg_pool),
            reranker_registry=_get_fallback_registry(),
            config=config,
        )

        # Cache it
        _override_cache[key] = pipeline
        logger.debug("Cached pipeline for key %s (cache size: %d)", key, len(_override_cache))

        return pipeline
    except (ImportError, ValueError, RuntimeError) as exc:
        logger.warning("Failed to create override pipeline for key %s: %s", key, exc)
        # Fallback to singleton if available, else minimal pipeline
        if _pipeline is not None:
            return _pipeline
        return _create_fallback_pipeline()


def close_shared_pipeline() -> None:
    """Close the shared pipeline and clear override cache. Safe to call repeatedly."""
    global _pipeline, _pipeline_settings, _override_cache  # noqa: PLW0602

    if _pipeline is not None:
        # Note: RagPipeline doesn't have a close method currently,
        # but we clean up the reference for consistency
        logger.info("Shared RagPipeline cleaned up")
        _pipeline = None
        _pipeline_settings = None

    if _override_cache:
        logger.info("Cleared %d override pipelines from cache", len(_override_cache))
        _override_cache.clear()


def _create_fallback_pipeline() -> Any:
    """Create a minimal pipeline that handles missing dependencies gracefully."""
    try:
        # Use settings to create a minimal pipeline
        from .config import RetrieverConfig
        from .pipeline import RagPipeline

        config = RetrieverConfig.from_env()

        return RagPipeline(
            retriever=_create_empty_retriever(),
            reranker_registry=_get_fallback_registry(),
            config=config,
        )
    except (ImportError, ValueError, RuntimeError):
        # Ultimate fallback - return an object with minimal interface
        return _MinimalFallbackPipeline()


def _create_empty_retriever() -> Any:
    """Create an empty retriever that returns no results."""

    class EmptyRetriever:
        async def ainvoke(self, *args, **kwargs):
            return {"chunks": []}

    return EmptyRetriever()


def _get_fallback_registry() -> Any:
    """Get a minimal reranker registry."""
    try:
        from .rerankers.registry import registry as fallback_registry

        return fallback_registry
    except ImportError:
        # Create a minimal registry
        class MinimalRegistry:
            def get_reranker(self, name):
                return None

        return MinimalRegistry()


class _MinimalFallbackPipeline:
    """Minimal pipeline interface for graceful degradation."""

    async def retrieve(self, query: str, top_k: int = 5, **kwargs) -> dict[str, Any]:
        return {"chunks": [], "chunk_count": 0, "top_score": 0.0, "source_uris": []}


def _build_retriever(config: Any, pg_pool: Any = None) -> Any:
    """Instantiate the retriever described by config (copied from pipeline.py).

    Args:
        config: RetrieverConfig or config-like object
        pg_pool: Optional asyncpg pool for BM25 retrieval

    Returns:
        Retriever instance
    """
    from .retrieval import BM25Retriever, HybridRetriever
    from .retrieval.vector_store_factory import create_vector_retriever

    vector_retriever = create_vector_retriever(config)

    # Handle different retrieval strategies
    strategy = getattr(config, "retrieval_strategy", None)
    if strategy is not None and hasattr(strategy, "value"):
        strategy = strategy.value  # Convert enum to string

    if strategy == "hybrid":
        if vector_retriever is None and pg_pool is None:
            logger.warning(
                "HYBRID strategy requested but neither vector store nor pg_pool "
                "is available — returning empty retriever"
            )
            return _create_empty_retriever()
        if vector_retriever is None:
            logger.warning(
                "HYBRID strategy requested but no vector store available — degrading to BM25-only"
            )
            return BM25Retriever(pg_pool=pg_pool)
        return HybridRetriever(
            vector_retriever=vector_retriever,
            bm25_retriever=BM25Retriever(pg_pool=pg_pool),
            config=config,
        )

    if strategy == "bm25":
        if pg_pool is None:
            logger.warning("BM25 strategy requested but pg_pool is not wired")
            return _create_empty_retriever()
        return BM25Retriever(pg_pool=pg_pool)

    if vector_retriever is not None:
        return vector_retriever
    return _create_empty_retriever()
