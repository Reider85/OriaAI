"""Checkpoint metrics for ADR-010 composite checkpointer."""

import logging
from typing import Any, Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
)

logger = logging.getLogger(__name__)


class CheckpointMetrics:
    """Metrics for checkpoint operations using Prometheus client.
    
    Metrics:
        - checkpoint_write_redis_latency_ms: Histogram for Redis write latency
        - checkpoint_write_pg_buffer_latency_ms: Histogram for PostgreSQL buffer write latency
        - checkpoint_read_redis_hit_count: Counter for Redis read hits
        - checkpoint_read_pg_fallback_count: Counter for PostgreSQL read fallbacks
        - checkpoint_write_redis_error_count: Counter for Redis write errors
        - checkpoint_write_pg_error_count: Counter for PostgreSQL write errors
        - checkpoint_write_both_failed_count: Counter for both-layer write failures
    """
    
    def __init__(
        self,
        registry: Optional[CollectorRegistry] = None,
        *,
        prefix: str = "llm_client_checkpoint",
    ) -> None:
        """Initialize checkpoint metrics.
        
        Args:
            registry: Optional Prometheus registry (default uses global registry)
            prefix: Metric prefix for all metrics
        """
        self.registry = registry or CollectorRegistry()
        self.prefix = prefix
        
        # Histograms for latencies (milliseconds)
        self.write_redis_latency = Histogram(
            f"{prefix}_write_redis_latency_ms",
            "Redis checkpoint write latency (milliseconds)",
            buckets=[0.1, 1, 5, 10, 25, 50, 100, 250, 500, 1000],
            registry=self.registry,
        )
        
        self.write_pg_buffer_latency = Histogram(
            f"{prefix}_write_pg_buffer_latency_ms",
            "PostgreSQL checkpoint buffer write latency (milliseconds)",
            buckets=[0.1, 1, 5, 10, 25, 50, 100, 250, 500, 1000],
            registry=self.registry,
        )
        
        # Counters for operations
        self.read_redis_hit = Counter(
            f"{prefix}_read_redis_hit_count",
            "Number of Redis read hits",
            registry=self.registry,
        )
        
        self.read_pg_fallback = Counter(
            f"{prefix}_read_pg_fallback_count",
            "Number of PostgreSQL read fallbacks",
            registry=self.registry,
        )
        
        self.write_redis_error = Counter(
            f"{prefix}_write_redis_error_count",
            "Number of Redis write errors",
            registry=self.registry,
        )
        
        self.write_pg_error = Counter(
            f"{prefix}_write_pg_error_count",
            "Number of PostgreSQL write errors",
            registry=self.registry,
        )
        
        self.write_both_failed = Counter(
            f"{prefix}_write_both_failed_count",
            "Number of both-layer write failures",
            registry=self.registry,
        )
        
        # Gauge for buffer size (if available from checkpointer)
        self.buffer_size = Gauge(
            f"{prefix}_buffer_size",
            "PostgreSQL checkpoint buffer size (if available)",
            registry=self.registry,
        )
        
        # Flusher-specific metrics
        self.flush_count = Counter(
            f"{prefix}_flush_count",
            "Number of flush operations performed",
            registry=self.registry,
        )
        
        self.flush_duration_ms = Histogram(
            f"{prefix}_flush_duration_ms",
            "PostgreSQL flush operation duration (milliseconds)",
            buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500],
            registry=self.registry,
        )
        
        self.flush_error_count = Counter(
            f"{prefix}_flush_error_count",
            "Number of flush errors (consecutive failures)",
            registry=self.registry,
        )
        
        self.flush_interval_seconds = Gauge(
            f"{prefix}_flush_interval_seconds",
            "Current flush interval in seconds (adaptive)",
            registry=self.registry,
        )
    
    def record_redis_write_latency(self, latency_ms: float) -> None:
        """Record Redis write latency.
        
        Args:
            latency_ms: Latency in milliseconds
        """
        self.write_redis_latency.observe(latency_ms)
    
    def record_pg_buffer_latency(self, latency_ms: float) -> None:
        """Record PostgreSQL buffer write latency.
        
        Args:
            latency_ms: Latency in milliseconds
        """
        self.write_pg_buffer_latency.observe(latency_ms)
    
    def increment_redis_hit(self) -> None:
        """Increment Redis read hit counter."""
        self.read_redis_hit.inc()
    
    def increment_pg_fallback(self) -> None:
        """Increment PostgreSQL read fallback counter."""
        self.read_pg_fallback.inc()
    
    def increment_redis_error(self) -> None:
        """Increment Redis write error counter."""
        self.write_redis_error.inc()
    
    def increment_pg_error(self) -> None:
        """Increment PostgreSQL write error counter."""
        self.write_pg_error.inc()
    
    def increment_both_failed(self) -> None:
        """Increment both-layer write failure counter."""
        self.write_both_failed.inc()
    
    def set_buffer_size(self, size: int) -> None:
        """Set PostgreSQL buffer size gauge.
        
        Args:
            size: Buffer size (number of checkpoints)
        """
        self.buffer_size.set(size)
    
    def increment_flush_count(self) -> None:
        """Increment flush operation counter."""
        self.flush_count.inc()
    
    def record_flush_duration(self, duration_ms: float) -> None:
        """Record flush operation duration.
        
        Args:
            duration_ms: Duration in milliseconds
        """
        self.flush_duration_ms.observe(duration_ms)
    
    def increment_flush_error(self) -> None:
        """Increment flush error counter."""
        self.flush_error_count.inc()
    
    def set_flush_interval(self, interval_seconds: float) -> None:
        """Set current flush interval gauge.
        
        Args:
            interval_seconds: Current flush interval in seconds
        """
        self.flush_interval_seconds.set(interval_seconds)
    
    def reset(self) -> None:
        """Reset all counters and gauges (useful for testing)."""
        for collector in self.registry._collector_to_names:
            if isinstance(collector, (Counter, Gauge)):
                collector._value._value = 0
                collector._value._labelvalues = None


class NullCheckpointMetrics(CheckpointMetrics):
    """No-op checkpoint metrics for tests or when metrics are disabled."""
    
    def __init__(self) -> None:
        """Initialize null metrics (no-op)."""
        # Override all methods to do nothing
        super().__init__(registry=CollectorRegistry())
        
    def record_redis_write_latency(self, latency_ms: float) -> None:
        pass
    
    def record_pg_buffer_latency(self, latency_ms: float) -> None:
        pass
    
    def increment_redis_hit(self) -> None:
        pass
    
    def increment_pg_fallback(self) -> None:
        pass
    
    def increment_redis_error(self) -> None:
        pass
    
    def increment_pg_error(self) -> None:
        pass
    
    def increment_both_failed(self) -> None:
        pass
    
    def set_buffer_size(self, size: int) -> None:
        pass
    
    def increment_flush_count(self) -> None:
        pass
    
    def record_flush_duration(self, duration_ms: float) -> None:
        pass
    
    def increment_flush_error(self) -> None:
        pass
    
    def set_flush_interval(self, interval_seconds: float) -> None:
        pass


# Default metrics instance for convenience
default_checkpoint_metrics: CheckpointMetrics = CheckpointMetrics()