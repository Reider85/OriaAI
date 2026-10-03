"""Shared RAG pipeline singleton for rag_query tool (ADR-003, Phase 2).

Implements singleton pattern to avoid recreating RagPipeline on every tool call,
which causes significant performance overhead with vector stores like Chroma.
"""

import logging
from typing import Any

from llm_client.config import Settings

logger = logging.getLogger(__name__)

_pipeline: Any = None
_pipeline_settings: Settings | None = None


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
        logger.info("Shared RagPipeline created for vector store: %s", 
                   settings.vector_store_kind or "none")
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


def close_shared_pipeline() -> None:
    """Close the shared pipeline if one was created. Safe to call repeatedly."""
    global _pipeline, _pipeline_settings
    if _pipeline is not None:
        # Note: RagPipeline doesn't have a close method currently,
        # but we clean up the reference for consistency
        logger.info("Shared RagPipeline cleaned up")
        _pipeline = None
        _pipeline_settings = None


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
        return {
            "chunks": [],
            "chunk_count": 0,
            "top_score": 0.0,
            "source_uris": []
        }