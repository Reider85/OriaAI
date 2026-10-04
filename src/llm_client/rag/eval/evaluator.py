"""RAG evaluator for quality metrics and A/B testing."""

import json
import time
from collections.abc import Iterator
from typing import Any

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.eval.mock_pipeline import MockRetrievalPipeline
from llm_client.rag.eval.models import CategoryReport, EvalReport, QueryResult

DEFAULT_RECALL_IMPROVEMENT_THRESHOLD = 15.0
DEFAULT_SEMANTIC_IMPROVEMENT_THRESHOLD = 15.0
DEFAULT_LATENCY_THRESHOLD_MS = 100.0


def improvement_percent(baseline: float, treatment: float) -> float | None:
    """Relative improvement in percent, or None when the baseline is zero.

    A zero baseline makes the relative ratio undefined. Reporting None keeps the
    JSON report valid (``float('inf')`` would serialize to a non-standard
    ``Infinity`` token) and lets the caller treat the case explicitly.
    """
    if baseline <= 0.0:
        return None
    return (treatment - baseline) / baseline * 100.0


class RAGEvaluator:
    """Evaluator for RAG pipeline quality metrics."""

    def __init__(self, eval_dataset_path: str, corpus: list[dict[str, Any]]):
        """Initialize evaluator with dataset and corpus.

        Args:
            eval_dataset_path: Path to evaluation dataset JSONL file
            corpus: List of documents for retrieval simulation
        """
        self.eval_dataset_path = eval_dataset_path
        self.dataset = self._load_dataset(eval_dataset_path)
        self.pipeline = MockRetrievalPipeline(corpus)

    def _load_dataset(self, path: str) -> list[dict[str, Any]]:
        """Load and validate the evaluation dataset from a JSONL file."""
        dataset: list[dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{lineno} is not valid JSON: {e}") from e
                self._validate_entry(entry, path, lineno)
                dataset.append(entry)
        return dataset

    @staticmethod
    def _validate_entry(entry: Any, path: str, lineno: int) -> None:
        """Validate one dataset entry, raising ValueError with a precise location."""
        where = f"{path}:{lineno}"
        if not isinstance(entry, dict):
            raise TypeError(f"{where}: entry must be a JSON object, got {type(entry).__name__}")
        for field in ("query", "category"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"{where}: '{field}' must be a non-empty string")
        relevant = entry.get("relevant_doc_ids")
        if not isinstance(relevant, list) or not relevant:
            raise ValueError(f"{where}: 'relevant_doc_ids' must be a non-empty list")
        bad = [r for r in relevant if not isinstance(r, str) or not r.strip()]
        if bad:
            raise ValueError(
                f"{where}: 'relevant_doc_ids' must contain non-empty strings, got {bad!r}"
            )

    async def evaluate(self, config: RetrieverConfig, *, limit: int | None = None) -> EvalReport:
        """Evaluate RAG pipeline with given configuration.

        Args:
            config: RetrieverConfig to test
            limit: Only evaluate the first N queries (used by the PR quick gate)

        Returns:
            EvalReport with recall@5 and per-category metrics
        """
        dataset = self.dataset if limit is None else self.dataset[:limit]
        if not dataset:
            raise ValueError(f"evaluation dataset is empty: {self.eval_dataset_path}")

        query_results = []

        # Evaluate each query
        for entry in dataset:
            query = entry["query"]
            relevant_doc_ids = entry["relevant_doc_ids"]
            category = entry["category"]

            # Perform search
            start_time = time.time()
            retrieved_docs = await self.pipeline.search(query, config)
            latency_ms = (time.time() - start_time) * 1000

            # Extract document IDs
            retrieved_ids = [doc["id"] for doc in retrieved_docs]

            # Calculate recall@5
            hit_at_5 = any(doc_id in relevant_doc_ids for doc_id in retrieved_ids[:5])

            # Store query result
            query_result = QueryResult(
                query=query,
                category=category,
                retrieved_ids=retrieved_ids,
                relevant_ids=relevant_doc_ids,
                hit_at_5=hit_at_5,
                latency_ms=latency_ms,
                retrieved_docs=retrieved_docs,
                relevant_docs=[
                    doc for doc in self.pipeline.corpus if doc["id"] in relevant_doc_ids
                ],
            )
            query_results.append(query_result)

        # Calculate overall metrics
        total_queries = len(query_results)
        recall_at_5 = sum(1 for qr in query_results if qr.hit_at_5) / total_queries
        avg_latency_ms = sum(qr.latency_ms for qr in query_results) / total_queries

        # Calculate per-category metrics
        category_results: dict[str, list[QueryResult]] = {}
        for query_result in query_results:
            category_results.setdefault(query_result.category, []).append(query_result)

        per_category = {}
        for category, results in category_results.items():
            category_queries = len(results)
            category_recall = sum(1 for r in results if r.hit_at_5) / category_queries
            category_latency = sum(r.latency_ms for r in results) / category_queries

            per_category[category] = CategoryReport(
                category=category,
                query_count=category_queries,
                recall_at_5=category_recall,
                avg_latency_ms=category_latency,
                query_results=results,
            )

        return EvalReport(
            recall_at_5=recall_at_5,
            avg_latency_ms=avg_latency_ms,
            per_category=per_category,
            query_results=query_results,
        )

    async def ab_test(
        self,
        baseline_config: RetrieverConfig,
        treatment_config: RetrieverConfig,
        *,
        limit: int | None = None,
        recall_improvement_threshold: float = DEFAULT_RECALL_IMPROVEMENT_THRESHOLD,
        semantic_improvement_threshold: float = DEFAULT_SEMANTIC_IMPROVEMENT_THRESHOLD,
        latency_threshold_ms: float = DEFAULT_LATENCY_THRESHOLD_MS,
    ) -> dict[str, Any]:
        """Run A/B test comparing baseline and treatment configurations.

        Pass criteria (ADR-017 / E-3):
            * overall recall@5 improvement >= recall_improvement_threshold
            * semantic-category recall@5 improvement >= semantic_improvement_threshold
            * latency overhead < latency_threshold_ms

        Args:
            baseline_config: Configuration without reranker (baseline)
            treatment_config: Configuration with reranker (treatment)
            limit: Only evaluate the first N queries (used by the PR quick gate)
            recall_improvement_threshold: Minimum overall recall@5 improvement, percent
            semantic_improvement_threshold: Minimum semantic recall@5 improvement, percent
            latency_threshold_ms: Maximum allowed treatment-minus-baseline latency

        Returns:
            Dictionary with A/B test results
        """
        # Evaluate both configurations on the same queries
        baseline_report = await self.evaluate(baseline_config, limit=limit)
        treatment_report = await self.evaluate(treatment_config, limit=limit)

        improvement = improvement_percent(baseline_report.recall_at_5, treatment_report.recall_at_5)
        latency_overhead = treatment_report.avg_latency_ms - baseline_report.avg_latency_ms

        # Per-category improvement — categories are reported separately on purpose:
        # exact_term recall is dominated by BM25, so aggregating it into a single
        # recall@5 would hide whether the reranker actually moved semantic quality.
        per_category_improvement: dict[str, Any] = {}
        for category, baseline_cat in baseline_report.per_category.items():
            treatment_cat = treatment_report.per_category.get(category)
            if treatment_cat is None:
                continue
            per_category_improvement[category] = {
                "query_count": baseline_cat.query_count,
                "baseline_recall_at_5": baseline_cat.recall_at_5,
                "treatment_recall_at_5": treatment_cat.recall_at_5,
                "improvement_percent": improvement_percent(
                    baseline_cat.recall_at_5, treatment_cat.recall_at_5
                ),
                "baseline_avg_latency_ms": baseline_cat.avg_latency_ms,
                "treatment_avg_latency_ms": treatment_cat.avg_latency_ms,
            }

        semantic_improvement = per_category_improvement.get("semantic", {}).get(
            "improvement_percent"
        )
        semantic_baseline = per_category_improvement.get("semantic", {}).get(
            "baseline_recall_at_5", 0.0
        )
        semantic_treatment = per_category_improvement.get("semantic", {}).get(
            "treatment_recall_at_5", 0.0
        )

        overall_pass = self._meets_threshold(
            improvement,
            treatment_report.recall_at_5,
            baseline_report.recall_at_5,
            recall_improvement_threshold,
        )
        semantic_pass = self._meets_threshold(
            semantic_improvement,
            semantic_treatment,
            semantic_baseline,
            semantic_improvement_threshold,
        )
        latency_pass = latency_overhead < latency_threshold_ms

        passes = overall_pass and semantic_pass and latency_pass

        return {
            "baseline": {
                "recall_at_5": baseline_report.recall_at_5,
                "avg_latency_ms": baseline_report.avg_latency_ms,
                "query_count": len(baseline_report.query_results),
                "per_category": {
                    cat: {
                        "recall_at_5": report.recall_at_5,
                        "avg_latency_ms": report.avg_latency_ms,
                        "query_count": report.query_count,
                    }
                    for cat, report in baseline_report.per_category.items()
                },
            },
            "treatment": {
                "recall_at_5": treatment_report.recall_at_5,
                "avg_latency_ms": treatment_report.avg_latency_ms,
                "query_count": len(treatment_report.query_results),
                "per_category": {
                    cat: {
                        "recall_at_5": report.recall_at_5,
                        "avg_latency_ms": report.avg_latency_ms,
                        "query_count": report.query_count,
                    }
                    for cat, report in treatment_report.per_category.items()
                },
            },
            "per_category_improvement": per_category_improvement,
            "improvement_percent": improvement,
            "semantic_improvement_percent": semantic_improvement,
            "latency_overhead_ms": latency_overhead,
            "passes": passes,
            "criteria": {
                "recall_improvement_threshold": recall_improvement_threshold,
                "semantic_improvement_threshold": semantic_improvement_threshold,
                "latency_threshold_ms": latency_threshold_ms,
                "actual_improvement": improvement,
                "actual_semantic_improvement": semantic_improvement,
                "actual_latency": latency_overhead,
                "overall_pass": overall_pass,
                "semantic_pass": semantic_pass,
                "latency_pass": latency_pass,
                "baseline_recall_zero": baseline_report.recall_at_5 <= 0.0,
            },
            "query_count": len(baseline_report.query_results),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "date": time.strftime("%Y-%m-%d"),
        }

    @staticmethod
    def _meets_threshold(
        improvement: float | None,
        treatment_value: float,
        baseline_value: float,
        threshold: float,
    ) -> bool:
        """Compare an improvement against its threshold.

        When the baseline is zero the relative improvement is undefined, so any
        strictly positive move counts as passing; no movement fails.
        """
        if improvement is None:
            return treatment_value > baseline_value
        return improvement >= threshold

    def iter_regressions(self, results: dict[str, Any]) -> Iterator[str]:
        """Yield human-readable descriptions of every failed PASS criterion."""
        criteria = results["criteria"]
        if not criteria["overall_pass"]:
            actual = criteria["actual_improvement"]
            actual_text = "undefined (zero baseline)" if actual is None else f"{actual:.1f}%"
            yield (
                f"recall@5 improvement {actual_text} < {criteria['recall_improvement_threshold']}%"
            )
        if not criteria["semantic_pass"]:
            actual = criteria["actual_semantic_improvement"]
            actual_text = "undefined (zero baseline)" if actual is None else f"{actual:.1f}%"
            yield (
                f"semantic recall@5 improvement {actual_text} < "
                f"{criteria['semantic_improvement_threshold']}%"
            )
        if not criteria["latency_pass"]:
            yield (
                f"latency overhead {criteria['actual_latency']:.1f}ms >= "
                f"{criteria['latency_threshold_ms']}ms"
            )
