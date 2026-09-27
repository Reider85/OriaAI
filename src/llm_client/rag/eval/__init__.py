"""RAG evaluation module for A/B testing and quality metrics."""

from .evaluator import RAGEvaluator
from .models import CategoryReport, EvalReport, QueryResult

__all__ = ["CategoryReport", "EvalReport", "QueryResult", "RAGEvaluator"]