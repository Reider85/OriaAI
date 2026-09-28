"""HybridRetriever for combining vector and BM25 retrieval with parallel execution."""

import asyncio
import logging
from typing import Any

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.metrics import RerankerMetrics, default_reranker_metrics
from llm_client.rag.retrieval.bm25_retriever import BM25Retriever

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Retriever that combines vector and BM25 retrieval with parallel execution.
    
    Implements ADR-020 hybrid retrieval: vector top-20 + BM25 top-20 → 
    returns both lists for fusion (RRF). Uses asyncio.gather for parallel
    execution to minimize latency (max(vector, bm25) not sum).
    """

    def __init__(
        self,
        vector_retriever,  # LangChain VectorStoreRetriever (injected dependency)
        bm25_retriever: BM25Retriever,
        config: RetrieverConfig,
        metrics: RerankerMetrics | None = None,
    ):
        """Initialize HybridRetriever.
        
        Args:
            vector_retriever: LangChain VectorStoreRetriever for vector similarity search
            bm25_retriever: BM25Retriever for PostgreSQL tsvector search
            config: RetrieverConfig with retrieval settings
            metrics: Optional metrics instance (defaults to global metrics)
        """
        self._vector = vector_retriever
        self._bm25 = bm25_retriever
        self._config = config
        self._metrics = metrics or default_reranker_metrics

    async def aretrieve(
        self,
        query: str,
        user_id: str,
        top_k_per_strategy: int | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Retrieve documents using both vector and BM25 strategies in parallel.
        
        Args:
            query: Search query string
            user_id: User ID for multi-tenancy filtering  
            top_k_per_strategy: Number of documents to retrieve per strategy
                               (defaults to config.vector_top_k / config.bm25_top_k)
        
        Returns:
            tuple of (vector_docs, bm25_docs), each up to top_k_per_strategy elements.
            Each document is in common dict format: {"id", "content", "metadata", "score"}
            
        Raises:
            RetrievalError: If both retrievers fail
        """
        if not query.strip():
            logger.warning("Empty query provided to HybridRetriever")
            return [], []
        
        # Use config defaults if not specified
        if top_k_per_strategy is None:
            top_k_per_strategy = self._config.vector_top_k
        
        # Record start time for latency metrics
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Execute both retrievals in parallel
            vector_task = self._vector.aget_relevant_documents(
                query, k=top_k_per_strategy
            )
            bm25_task = self._bm25.retrieve(query, user_id, top_k_per_strategy)
            
            # Run both tasks with exception handling
            vector_docs, bm25_docs = await asyncio.gather(
                vector_task, bm25_task, return_exceptions=True
            )
            
            # Handle partial failures and normalize results
            vector_failed = isinstance(vector_docs, Exception)
            bm25_failed = isinstance(bm25_docs, Exception)
            
            if vector_failed:
                error_msg = f"Vector retrieval failed: {vector_docs!s}"
                logger.warning("hybrid_vector_failure: %s", error_msg)
                self._metrics.increment_error_count()
                vector_docs = []
            else:
                # Normalize vector docs to common format (always do this)
                vector_docs = self._normalize_vector_docs(vector_docs)
            
            if bm25_failed:
                error_msg = f"BM25 retrieval failed: {bm25_docs!s}"
                logger.warning("hybrid_bm25_failure: %s", error_msg)
                self._metrics.increment_error_count()
                bm25_docs = []
            
            # If both retrievers failed, raise RetrievalError
            if vector_failed and bm25_failed:
                raise RetrievalError("Both vector and BM25 retrieval failed")
            
            # Record metrics
            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            self._metrics.record_latency(latency_ms)
            
            # Log retrieval results
            logger.debug(
                "HybridRetriever completed: vector=%d, bm25=%d, latency=%.2fms",
                len(vector_docs),
                len(bm25_docs),
                latency_ms
            )
            
            return vector_docs, bm25_docs
            
        except Exception as e:
            # Log and increment error counter (only for unexpected errors, not handled failures)
            logger.error("HybridRetriever failed for query='%s': %s", query, str(e))
            # Only increment if not already handled by individual failure cases
            if not (vector_failed and bm25_failed):
                self._metrics.increment_error_count()
            raise RetrievalError(f"Hybrid retrieval failed: {e!s}") from e

    def _normalize_vector_docs(self, vector_docs: list[Any]) -> list[dict]:
        """Convert LangChain Document objects to common dict format.
        
        Args:
            vector_docs: List of LangChain Document objects from vector retrieval
            
        Returns:
            List of documents in common format: {"id", "content", "metadata", "score"}
        """
        normalized_docs = []
        
        for i, doc in enumerate(vector_docs):
            # LangChain Document has page_content and metadata
            # Extract score if available (some vector stores add it)
            # Use the document's score if present, otherwise generate synthetic score
            if hasattr(doc, 'score') and doc.score is not None:
                score = float(doc.score)  # Use document's original score
            else:
                score = 1.0 / (i + 1)  # Fallback synthetic score based on rank
            
            # Handle id: LangChain Document doesn't have id by default
            # Use document hash or generate synthetic id
            doc_id = getattr(doc, "id", None)
            if doc_id is None:
                # Generate synthetic id from content hash
                import hashlib
                content_hash = hashlib.md5(doc.page_content.encode()).hexdigest()
                doc_id = f"vector_{i}_{content_hash[:8]}"
            
            normalized_doc = {
                "id": doc_id,
                "content": doc.page_content,
                "metadata": doc.metadata or {},
                "score": score,
            }
            normalized_docs.append(normalized_doc)
        
        return normalized_docs


class RetrievalError(Exception):
    """Exception raised when hybrid retrieval fails completely."""
