"""Reciprocal Rank Fusion (RRF) implementation for RAG pipeline."""

import logging
import time
from typing import Any

from prometheus_client import CollectorRegistry, Gauge, Histogram

logger = logging.getLogger(__name__)


def rrf_fusion(
    vector_docs: list[dict[str, Any]],
    bm25_docs: list[dict[str, Any]],
    top_k: int = 50,
    k_constant: int = 60,
    vector_weight: float = 0.5,
    bm25_weight: float = 0.5,
) -> list[dict[str, Any]]:
    """Fuse two ranked lists using Reciprocal Rank Fusion.

    Args:
        vector_docs: Documents from vector retrieval (already ranked)
        bm25_docs: Documents from BM25 retrieval (already ranked)
        top_k: Number of documents to return after fusion
        k_constant: RRF constant (typically 60, Cormack et al. 2009)
        vector_weight: Weight for vector similarity scores (0.0-1.0)
        bm25_weight: Weight for BM25 scores (0.0-1.0)

    Returns:
        Top-K unique documents sorted by RRF score descending, with "rrf_score" field

    Raises:
        ValueError: If weights don't sum to 1.0 or are invalid
    """
    # Validate weights
    if not (0 < vector_weight < 1 and 0 < bm25_weight < 1):
        raise ValueError("vector_weight and bm25_weight must be between 0 and 1")
    if abs(vector_weight + bm25_weight - 1.0) > 1e-10:
        raise ValueError("vector_weight + bm25_weight must equal 1.0")

    # Create score tracking and document mapping
    scores: dict[str, float] = {}
    docs_by_id: dict[str, dict[str, Any]] = {}
    overlap_count = 0

    # Process vector documents
    for rank, doc in enumerate(vector_docs, start=1):
        doc_id = doc.get("id", f"vector_{rank}")
        if doc_id in scores:
            overlap_count += 1
        scores[doc_id] = scores.get(doc_id, 0.0) + vector_weight / (k_constant + rank)
        docs_by_id[doc_id] = doc

    # Process BM25 documents
    for rank, doc in enumerate(bm25_docs, start=1):
        doc_id = doc.get("id", f"bm25_{rank}")
        if doc_id in scores:
            overlap_count += 1
        scores[doc_id] = scores.get(doc_id, 0.0) + bm25_weight / (k_constant + rank)
        docs_by_id[doc_id] = doc

    # Sort by RRF score and return top_k
    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    fused_docs = []

    for doc_id, score in sorted_ids[:top_k]:
        doc = docs_by_id[doc_id].copy()
        doc["rrf_score"] = score
        # Ensure all documents have an "id" field
        if "id" not in doc:
            # This shouldn't happen since we generate fallback IDs in the loops above,
            # but just to be safe
            doc["id"] = doc_id
        fused_docs.append(doc)

    return fused_docs


class FusionMetrics:
    """Metrics for RAG fusion operations using Prometheus client.

    Metrics:
        - rag_fusion_latency_ms: Histogram for fusion latency (milliseconds)
        - rag_fusion_input_count: Gauge for number of input documents
        - rag_fusion_output_count: Gauge for number of output documents
        - rag_fusion_overlap_count: Gauge for overlap count
    """

    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        *,
        prefix: str = "llm_client_rag_fusion",
    ) -> None:
        """Initialize fusion metrics.

        Args:
            registry: Optional Prometheus registry (default uses global registry)
            prefix: Metric prefix for all metrics
        """
        self.registry = registry or CollectorRegistry()
        self.prefix = prefix

        # Histogram for latency (milliseconds)
        self.fusion_latency = Histogram(
            f"{prefix}_latency_ms",
            "Fusion operation latency (milliseconds)",
            buckets=[1, 5, 10, 25, 50, 100, 200, 500],
            registry=self.registry,
        )

        # Gauges for input/output counts
        self.fusion_input_count = Gauge(
            f"{prefix}_input_count",
            "Number of input documents to fusion",
            registry=self.registry,
        )

        self.fusion_output_count = Gauge(
            f"{prefix}_output_count",
            "Number of output documents from fusion",
            registry=self.registry,
        )

        self.fusion_overlap_count = Gauge(
            f"{prefix}_overlap_count",
            "Number of overlapping documents between retrievers",
            registry=self.registry,
        )

    def record_latency(self, latency_ms: float) -> None:
        """Record fusion latency in milliseconds.

        Args:
            latency_ms: Latency in milliseconds
        """
        self.fusion_latency.observe(latency_ms)

    def set_input_count(self, count: int) -> None:
        """Set the number of input documents.

        Args:
            count: Number of input documents
        """
        self.fusion_input_count.set(count)

    def set_output_count(self, count: int) -> None:
        """Set the number of output documents.

        Args:
            count: Number of output documents
        """
        self.fusion_output_count.set(count)

    def set_overlap_count(self, count: int) -> None:
        """Set the number of overlapping documents.

        Args:
            count: Number of overlapping documents
        """
        self.fusion_overlap_count.set(count)

    def reset(self) -> None:
        """Reset all counters and gauges (useful for testing)."""
        for collector in self.registry._collector_to_names:
            if isinstance(collector, (Gauge)):
                collector._value._value = 0
                collector._value._labelvalues = None


class NullFusionMetrics(FusionMetrics):
    """No-op fusion metrics for tests or when metrics are disabled."""

    def __init__(self) -> None:
        """Initialize null metrics (no-op)."""
        # Override all methods to do nothing
        super().__init__(registry=CollectorRegistry())

    def record_latency(self, latency_ms: float) -> None:
        pass

    def set_input_count(self, count: int) -> None:
        pass

    def set_output_count(self, count: int) -> None:
        pass

    def set_overlap_count(self, count: int) -> None:
        pass


# Default metrics instance for convenience
default_fusion_metrics: FusionMetrics = FusionMetrics()


def rrf_fusion_with_metrics(
    vector_docs: list[dict[str, Any]],
    bm25_docs: list[dict[str, Any]],
    top_k: int = 50,
    k_constant: int = 60,
    vector_weight: float = 0.5,
    bm25_weight: float = 0.5,
    metrics: FusionMetrics | None = None,
) -> list[dict[str, Any]]:
    """RRF fusion with metrics recording.

    This is a convenience wrapper that records metrics around the core rrf_fusion function.

    Args:
        vector_docs: Documents from vector retrieval
        bm25_docs: Documents from BM25 retrieval
        top_k: Number of documents to return after fusion
        k_constant: RRF constant
        vector_weight: Weight for vector similarity
        bm25_weight: Weight for BM25 scores
        metrics: Optional metrics instance (defaults to global)

    Returns:
        Top-K fused documents
    """
    # Use global instance if not provided
    metrics = metrics or default_fusion_metrics

    # Record input counts
    input_count = len(vector_docs) + len(bm25_docs)
    metrics.set_input_count(input_count)

    # Record start time
    start_time = time.time()

    try:
        # Perform fusion
        result = rrf_fusion(
            vector_docs=vector_docs,
            bm25_docs=bm25_docs,
            top_k=top_k,
            k_constant=k_constant,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
        )

        # Record metrics
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_latency(latency_ms)
        metrics.set_output_count(len(result))

        # Count overlap (documents present in both lists)
        vector_ids = {doc.get("id", str(i)) for i, doc in enumerate(vector_docs)}
        bm25_ids = {doc.get("id", str(i)) for i, doc in enumerate(bm25_docs)}
        overlap = len(vector_ids & bm25_ids)
        metrics.set_overlap_count(overlap)

        return result

    except Exception as e:
        # Record error latency and re-raise
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_latency(latency_ms)
        logger.error("RRF fusion failed: %s", str(e))
        raise
