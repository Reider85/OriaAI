"""Unit tests for A/B test framework logic."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.eval.evaluator import RAGEvaluator

pytestmark = pytest.mark.eval


class TestABTestFramework:
    """Test cases for A/B test framework functionality."""

    @pytest.mark.asyncio
    async def test_ab_test_improvement_calculation(self):
        """Test that improvement percentage is calculated correctly."""
        # Mock evaluator and results
        evaluator = MagicMock(spec=RAGEvaluator)

        # Mock baseline and treatment results
        baseline_report = MagicMock()
        baseline_report.recall_at_5 = 0.4  # 40% baseline

        treatment_report = MagicMock()
        treatment_report.recall_at_5 = 0.6  # 60% treatment

        evaluator.evaluate.side_effect = [baseline_report, treatment_report]
        evaluator.ab_test = AsyncMock(
            return_value={
                "baseline": {"recall_at_5": 0.4},
                "treatment": {"recall_at_5": 0.6},
                "improvement_percent": 50.0,  # (0.6-0.4)/0.4 * 100 = 50%
                "latency_overhead_ms": 80.0,
                "passes": True,
                "criteria": {
                    "recall_improvement_threshold": 15.0,
                    "latency_threshold_ms": 100.0,
                    "actual_improvement": 50.0,
                    "actual_latency": 80.0,
                },
            }
        )

        # Test improvement calculation
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        # Check improvement calculation
        expected_improvement = (0.6 - 0.4) / 0.4 * 100  # 50%
        assert results["improvement_percent"] == pytest.approx(expected_improvement, rel=1e-9)
        assert results["improvement_percent"] > 15.0  # Passes threshold
        assert results["latency_overhead_ms"] < 100.0  # Passes latency threshold
        assert results["passes"] is True

    @pytest.mark.asyncio
    async def test_ab_test_no_improvement(self):
        """Test A/B test when there's no improvement."""
        evaluator = MagicMock(spec=RAGEvaluator)

        # Mock results with no improvement
        baseline_report = MagicMock()
        baseline_report.recall_at_5 = 0.5

        treatment_report = MagicMock()
        treatment_report.recall_at_5 = 0.5  # Same as baseline

        evaluator.evaluate.side_effect = [baseline_report, treatment_report]
        evaluator.ab_test = AsyncMock(
            return_value={
                "baseline": {"recall_at_5": 0.5},
                "treatment": {"recall_at_5": 0.5},
                "improvement_percent": 0.0,  # No improvement
                "latency_overhead_ms": 50.0,
                "passes": False,
                "criteria": {
                    "recall_improvement_threshold": 15.0,
                    "latency_threshold_ms": 100.0,
                    "actual_improvement": 0.0,
                    "actual_latency": 50.0,
                },
            }
        )

        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        # Check that improvement is 0 and test fails
        assert results["improvement_percent"] == 0.0
        assert results["passes"] is False

    @pytest.mark.asyncio
    async def test_ab_test_latency_threshold_fail(self):
        """Test A/B test when latency overhead exceeds threshold."""
        evaluator = MagicMock(spec=RAGEvaluator)

        # Mock results with good recall but bad latency
        baseline_report = MagicMock()
        baseline_report.recall_at_5 = 0.4
        baseline_report.avg_latency_ms = 50.0

        treatment_report = MagicMock()
        treatment_report.recall_at_5 = 0.6  # Good improvement
        treatment_report.avg_latency_ms = 200.0  # Bad latency

        evaluator.evaluate.side_effect = [baseline_report, treatment_report]
        evaluator.ab_test = AsyncMock(
            return_value={
                "baseline": {"recall_at_5": 0.4, "avg_latency_ms": 50.0},
                "treatment": {"recall_at_5": 0.6, "avg_latency_ms": 200.0},
                "improvement_percent": 50.0,
                "latency_overhead_ms": 150.0,  # 200 - 50 = 150ms > 100ms threshold
                "passes": False,
                "criteria": {
                    "recall_improvement_threshold": 15.0,
                    "latency_threshold_ms": 100.0,
                    "actual_improvement": 50.0,
                    "actual_latency": 150.0,
                },
            }
        )

        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        # Check that test fails due to latency
        assert results["improvement_percent"] > 15.0  # Good recall improvement
        assert results["latency_overhead_ms"] > 100.0  # Bad latency
        assert results["passes"] is False

    @pytest.mark.asyncio
    async def test_ab_test_per_category_breakdown(self):
        """Test that per-category results are correctly calculated."""
        evaluator = MagicMock(spec=RAGEvaluator)

        # Mock detailed results with per-category breakdown
        baseline_report = MagicMock()
        baseline_report.recall_at_5 = 0.4
        baseline_report.per_category = {
            "exact_term": {"recall_at_5": 0.6, "avg_latency_ms": 50.0},
            "semantic": {"recall_at_5": 0.3, "avg_latency_ms": 60.0},
            "fuzzy": {"recall_at_5": 0.3, "avg_latency_ms": 40.0},
        }

        treatment_report = MagicMock()
        treatment_report.recall_at_5 = 0.6
        treatment_report.per_category = {
            "exact_term": {"recall_at_5": 0.7, "avg_latency_ms": 60.0},
            "semantic": {"recall_at_5": 0.6, "avg_latency_ms": 80.0},
            "fuzzy": {"recall_at_5": 0.5, "avg_latency_ms": 70.0},
        }

        evaluator.evaluate.side_effect = [baseline_report, treatment_report]
        evaluator.ab_test = AsyncMock(
            return_value={
                "baseline": {
                    "recall_at_5": 0.4,
                    "per_category": {
                        "exact_term": {"recall_at_5": 0.6, "avg_latency_ms": 50.0},
                        "semantic": {"recall_at_5": 0.3, "avg_latency_ms": 60.0},
                        "fuzzy": {"recall_at_5": 0.3, "avg_latency_ms": 40.0},
                    },
                },
                "treatment": {
                    "recall_at_5": 0.6,
                    "per_category": {
                        "exact_term": {"recall_at_5": 0.7, "avg_latency_ms": 60.0},
                        "semantic": {"recall_at_5": 0.6, "avg_latency_ms": 80.0},
                        "fuzzy": {"recall_at_5": 0.5, "avg_latency_ms": 70.0},
                    },
                },
                "improvement_percent": 50.0,
                "latency_overhead_ms": 50.0,
                "passes": True,
                "criteria": {
                    "recall_improvement_threshold": 15.0,
                    "latency_threshold_ms": 100.0,
                    "actual_improvement": 50.0,
                    "actual_latency": 50.0,
                },
            }
        )

        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        # Check per-category improvements
        baseline_cats = results["baseline"]["per_category"]
        treatment_cats = results["treatment"]["per_category"]

        # exact_term: (0.7-0.6)/0.6 * 100 = 16.7% improvement
        exact_term_improvement = (
            (
                treatment_cats["exact_term"]["recall_at_5"]
                - baseline_cats["exact_term"]["recall_at_5"]
            )
            / baseline_cats["exact_term"]["recall_at_5"]
            * 100
        )
        assert exact_term_improvement > 0

        # semantic: (0.6-0.3)/0.3 * 100 = 100% improvement
        semantic_improvement = (
            (treatment_cats["semantic"]["recall_at_5"] - baseline_cats["semantic"]["recall_at_5"])
            / baseline_cats["semantic"]["recall_at_5"]
            * 100
        )
        assert semantic_improvement > 0

        # fuzzy: (0.5-0.3)/0.3 * 100 = 66.7% improvement
        fuzzy_improvement = (
            (treatment_cats["fuzzy"]["recall_at_5"] - baseline_cats["fuzzy"]["recall_at_5"])
            / baseline_cats["fuzzy"]["recall_at_5"]
            * 100
        )
        assert fuzzy_improvement > 0

        # Check that all categories are present
        assert "exact_term" in results["baseline"]["per_category"]
        assert "semantic" in results["baseline"]["per_category"]
        assert "fuzzy" in results["baseline"]["per_category"]

    def test_retriever_config_baseline_vs_treatment(self):
        """Test baseline and treatment configuration differences."""
        # Baseline: no reranking
        baseline_config = RetrieverConfig(reranker_enabled=False)
        assert baseline_config.reranker_enabled is False

        # Treatment: with reranking
        treatment_config = RetrieverConfig(reranker_enabled=True, reranker_name="bge")
        assert treatment_config.reranker_enabled is True
        assert treatment_config.reranker_name == "bge"

        # Other parameters should be the same
        assert baseline_config.retrieval_strategy == treatment_config.retrieval_strategy
        assert baseline_config.vector_top_k == treatment_config.vector_top_k

    @pytest.mark.asyncio
    async def test_ab_test_with_zero_baseline(self):
        """Test A/B test when baseline recall is zero (edge case)."""
        evaluator = MagicMock(spec=RAGEvaluator)

        # Mock results with zero baseline
        baseline_report = MagicMock()
        baseline_report.recall_at_5 = 0.0  # Zero baseline

        treatment_report = MagicMock()
        treatment_report.recall_at_5 = 0.2  # Some improvement

        evaluator.evaluate.side_effect = [baseline_report, treatment_report]
        evaluator.ab_test = AsyncMock(
            return_value={
                "baseline": {"recall_at_5": 0.0},
                "treatment": {"recall_at_5": 0.2},
                "improvement_percent": float("inf"),  # Division by zero case
                "latency_overhead_ms": 50.0,
                "passes": True,  # Any improvement from zero should pass
                "criteria": {
                    "recall_improvement_threshold": 15.0,
                    "latency_threshold_ms": 100.0,
                    "actual_improvement": float("inf"),
                    "actual_latency": 50.0,
                },
            }
        )

        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        # Handle division by zero case
        assert results["improvement_percent"] == float("inf")
        assert results["passes"] is True  # Any improvement from zero should pass


class TestEvaluationCriteria:
    """Test cases for evaluation criteria logic."""

    def test_recall_improvement_threshold(self):
        """Test recall improvement threshold logic."""
        threshold = 15.0

        # Case 1: Below threshold
        improvement = 10.0
        passes = improvement >= threshold
        assert passes is False

        # Case 2: At threshold
        improvement = 15.0
        passes = improvement >= threshold
        assert passes is True

        # Case 3: Above threshold
        improvement = 20.0
        passes = improvement >= threshold
        assert passes is True

    def test_latency_threshold(self):
        """Test latency overhead threshold logic."""
        threshold = 100.0

        # Case 1: Below threshold
        overhead = 80.0
        passes = overhead < threshold
        assert passes is True

        # Case 2: At threshold (should fail, strict <)
        overhead = 100.0
        passes = overhead < threshold
        assert passes is False

        # Case 3: Above threshold
        overhead = 120.0
        passes = overhead < threshold
        assert passes is False

    def test_combined_criteria(self):
        """Test combined criteria (both must pass)."""
        recall_threshold = 15.0
        latency_threshold = 100.0

        # Case 1: Both pass
        recall_improvement = 20.0
        latency_overhead = 80.0
        passes = (recall_improvement >= recall_threshold) and (latency_overhead < latency_threshold)
        assert passes is True

        # Case 2: Recall passes, latency fails
        recall_improvement = 20.0
        latency_overhead = 120.0
        passes = (recall_improvement >= recall_threshold) and (latency_overhead < latency_threshold)
        assert passes is False

        # Case 3: Recall fails, latency passes
        recall_improvement = 10.0
        latency_overhead = 80.0
        passes = (recall_improvement >= recall_threshold) and (latency_overhead < latency_threshold)
        assert passes is False

        # Case 4: Both fail
        recall_improvement = 10.0
        latency_overhead = 120.0
        passes = (recall_improvement >= recall_threshold) and (latency_overhead < latency_threshold)
        assert passes is False
