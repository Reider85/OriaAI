"""RAG evaluation module for A/B testing and quality metrics."""

from .corpus import build_eval_corpus
from .evaluator import (
    DEFAULT_LATENCY_THRESHOLD_MS,
    DEFAULT_RECALL_IMPROVEMENT_THRESHOLD,
    DEFAULT_SEMANTIC_IMPROVEMENT_THRESHOLD,
    RAGEvaluator,
    improvement_percent,
)
from .models import CategoryReport, EvalReport, QueryResult

__all__ = [
    "DEFAULT_LATENCY_THRESHOLD_MS",
    "DEFAULT_RECALL_IMPROVEMENT_THRESHOLD",
    "DEFAULT_SEMANTIC_IMPROVEMENT_THRESHOLD",
    "CategoryReport",
    "EvalReport",
    "QueryResult",
    "RAGEvaluator",
    "build_eval_corpus",
    "improvement_percent",
]
