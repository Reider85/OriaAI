"""RAG (Retrieval-Augmented Generation) reranking metrics using Prometheus client."""

import logging

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)

logger = logging.getLogger(__name__)


class RerankerMetrics:
    """Metrics for RAG reranking operations using Prometheus client.
    
    Metrics:
        - rag_rerank_latency_ms: Histogram for reranking latency (milliseconds)
        - rag_rerank_input_count: Gauge for number of input documents
        - rag_rerank_output_count: Gauge for number of output documents  
        - rag_rerank_error_count: Counter for reranking errors
    """
    
    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        *,
        prefix: str = "llm_client_reranker",
    ) -> None:
        """Initialize reranker metrics.
        
        Args:
            registry: Optional Prometheus registry (default uses global registry)
            prefix: Metric prefix for all metrics
        """
        self.registry = registry or CollectorRegistry()
        self.prefix = prefix
        
        # Histogram for latency (milliseconds)
        self.rerank_latency = Histogram(
            f"{prefix}_latency_ms",
            "Reranking operation latency (milliseconds)",
            buckets=[10, 25, 50, 100, 150, 200, 500, 1000, 2000],
            registry=self.registry,
        )
        
        # Gauges for input/output counts
        self.rerank_input_count = Gauge(
            f"{prefix}_input_count",
            "Number of input documents to reranking",
            registry=self.registry,
        )
        
        self.rerank_output_count = Gauge(
            f"{prefix}_output_count",
            "Number of output documents from reranking",
            registry=self.registry,
        )
        
        # Counter for errors
        self.rerank_error_count = Counter(
            f"{prefix}_error_count",
            "Number of reranking errors (exceptions)",
            registry=self.registry,
        )
    
    def record_latency(self, latency_ms: float) -> None:
        """Record reranking latency in milliseconds.
        
        Args:
            latency_ms: Latency in milliseconds
        """
        self.rerank_latency.observe(latency_ms)
    
    def set_input_count(self, count: int) -> None:
        """Set the number of input documents.
        
        Args:
            count: Number of input documents
        """
        self.rerank_input_count.set(count)
    
    def set_output_count(self, count: int) -> None:
        """Set the number of output documents.
        
        Args:
            count: Number of output documents
        """
        self.rerank_output_count.set(count)
    
    def increment_error_count(self) -> None:
        """Increment the reranking error counter."""
        self.rerank_error_count.inc()
    
    def reset(self) -> None:
        """Reset all counters and gauges (useful for testing)."""
        for collector in self.registry._collector_to_names:
            if isinstance(collector, (Counter, Gauge)):
                collector._value._value = 0
                collector._value._labelvalues = None


class NullRerankerMetrics(RerankerMetrics):
    """No-op reranker metrics for tests or when metrics are disabled."""
    
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
    
    def increment_error_count(self) -> None:
        pass


# Default metrics instance for convenience
default_reranker_metrics: RerankerMetrics = RerankerMetrics()