"""Evaluation models for RAG quality metrics."""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryResult:
    """Result for a single query evaluation."""

    query: str
    category: str
    retrieved_ids: list[str]
    relevant_ids: list[str]
    hit_at_5: bool
    latency_ms: float
    retrieved_docs: list[dict[str, Any]] = field(default_factory=list)
    relevant_docs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CategoryReport:
    """Report for a specific category (exact_term, semantic, fuzzy)."""

    category: str
    query_count: int
    recall_at_5: float
    avg_latency_ms: float
    query_results: list[QueryResult] = field(default_factory=list)


@dataclass
class EvalReport:
    """Complete evaluation report for RAG pipeline."""

    recall_at_5: float
    avg_latency_ms: float
    per_category: dict[str, CategoryReport]
    query_results: list[QueryResult]
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "recall_at_5": self.recall_at_5,
            "avg_latency_ms": self.avg_latency_ms,
            "per_category": {
                cat: {
                    "category": report.category,
                    "query_count": report.query_count,
                    "recall_at_5": report.recall_at_5,
                    "avg_latency_ms": report.avg_latency_ms,
                }
                for cat, report in self.per_category.items()
            },
            "query_results": [
                {
                    "query": qr.query,
                    "category": qr.category,
                    "retrieved_ids": qr.retrieved_ids,
                    "relevant_ids": qr.relevant_ids,
                    "hit_at_5": qr.hit_at_5,
                    "latency_ms": qr.latency_ms,
                }
                for qr in self.query_results
            ],
            "timestamp": self.timestamp,
        }
