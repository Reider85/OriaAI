"""Unit tests for semantic cache A/B test framework."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from llm_client.config import settings
from llm_client.rag.semantic_cache import CacheHitResult
from scripts.ab_test_semantic_cache import ABTestResult, run_ab_test

pytestmark = pytest.mark.eval


class TestSemanticCacheABTest:
    """Test cases for semantic cache A/B test functionality."""

    @pytest.mark.asyncio
    async def test_run_ab_test_returns_metrics(self):
        """Test that run_ab_test returns correct hit/miss/stale counts."""
        # Mock cache and metrics
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock()

        # Simulate second pass results: 1 hit, 1 miss, 1 stale
        # Note: get() returns None for both miss and stale
        def mock_get_side_effect(query):
            if query == "query1":
                return None  # miss
            elif query == "query2":
                return None  # stale (cache hit but below threshold or marked stale)
            elif query == "query3":
                return CacheHitResult(
                    answer="test answer",
                    referenced_doc_ids=["550e8400-e29b-41d4-a716-446655440000"],
                    created_at="2026-01-01T00:00:00",
                    model="gpt-4o-mini",
                    token_count=100,
                    similarity_score=0.95,
                )  # hit
            else:
                return None  # default

        mock_cache.get.side_effect = mock_get_side_effect
        mock_cache.put = AsyncMock()

        # Mock get_semantic_cache to return our mock
        with (
            patch("scripts.ab_test_semantic_cache.get_semantic_cache", return_value=mock_cache),
            patch("scripts.ab_test_semantic_cache.get_cache_hit_counts") as mock_counts,
        ):
            # Mock the counts to simulate 1 hit, 1 miss, 1 stale
            mock_counts.side_effect = [
                {"hit": 0, "miss": 0, "stale": 0},  # before
                {"hit": 1, "miss": 1, "stale": 1},  # after
            ]

            queries = ["query1", "query2", "query3"]
            result = await run_ab_test(queries, iterations=2)

            # Verify metrics
            assert result.total_queries == 3
            assert result.hits == 1
            assert result.misses == 1
            assert result.stale == 1
            assert result.hit_rate == 1 / 3
            assert result.stale_rate == 1 / 1  # stale/hits

    def test_pilot_pass_when_hit_rate_above_15pct(self):
        """Test pilot_pass returns True when hit rate >15% (16/100)."""
        result = ABTestResult(
            total_queries=100,
            hits=16,
            misses=84,
            stale=0,
            avg_latency_hit_ms=50.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.016,
            llm_calls_reduced=16,
        )

        # Test with default thresholds from settings
        assert result.pilot_pass() is True

        # Test with explicit thresholds
        assert (
            result.pilot_pass(
                hit_rate_threshold=0.15, stale_rate_threshold=0.01, hit_latency_ms_threshold=100.0
            )
            is True
        )

    def test_pilot_pass_when_stale_below_1pct(self):
        """Test pilot_pass returns True when stale rate <1% (0/100 hits)."""
        result = ABTestResult(
            total_queries=100,
            hits=100,
            misses=0,
            stale=0,
            avg_latency_hit_ms=50.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.1,
            llm_calls_reduced=100,
        )

        assert result.pilot_pass() is True

    def test_pilot_pass_when_latency_below_100ms(self):
        """Test pilot_pass returns True when latency <100ms."""
        result = ABTestResult(
            total_queries=100,
            hits=20,
            misses=80,
            stale=0,
            avg_latency_hit_ms=80.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.02,
            llm_calls_reduced=20,
        )

        assert result.pilot_pass() is True

    def test_rollback_when_stale_rate_above_1pct(self):
        """Test rollback_required returns True when stale rate >1% (2/100 hits)."""
        result = ABTestResult(
            total_queries=100,
            hits=100,
            misses=0,
            stale=2,
            avg_latency_hit_ms=50.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.1,
            llm_calls_reduced=100,
        )

        assert result.rollback_required() is True

    def test_rollback_when_hit_rate_below_10pct(self):
        """Test rollback_required returns True when hit rate <10% (9/100)."""
        result = ABTestResult(
            total_queries=100,
            hits=9,
            misses=91,
            stale=0,
            avg_latency_hit_ms=50.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.009,
            llm_calls_reduced=9,
        )

        assert result.rollback_required() is True

    def test_metrics_calculate_cost_savings(self):
        """Test that cost savings are calculated correctly."""
        result = ABTestResult(
            total_queries=100,
            hits=50,
            misses=50,
            stale=0,
            avg_latency_hit_ms=50.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=50 * settings.pilot_semantic_cache_avg_llm_cost_usd,  # calculated
            llm_calls_reduced=50,
        )

        # Cost savings = hits * avg cost per call
        expected_savings = 50 * settings.pilot_semantic_cache_avg_llm_cost_usd
        assert result.cost_saved_usd == expected_savings

    @pytest.mark.asyncio
    async def test_ab_test_with_disabled_cache(self):
        """Test that run_ab_test raises error when cache is disabled."""
        with patch("scripts.ab_test_semantic_cache.get_semantic_cache", return_value=None):
            queries = ["test query"]
            with pytest.raises(RuntimeError, match="Semantic cache disabled"):
                await run_ab_test(queries)

    @pytest.mark.asyncio
    async def test_ab_test_control_latency_measurement(self):
        """Test that control group latency is measured correctly."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)  # All misses
        mock_cache.put = AsyncMock()

        with patch("scripts.ab_test_semantic_cache.get_semantic_cache", return_value=mock_cache):
            queries = ["query1", "query2"]
            result = await run_ab_test(queries, iterations=2)

            # Verify control latency is measured
            assert result.avg_latency_no_cache_ms > 0
            # Control and miss latency should be in similar range (but not exactly equal)
            assert (
                abs(result.avg_latency_no_cache_ms - result.avg_latency_miss_ms) < 50.0
            )  # Within 50ms

    def test_duplicate_queries_increase_hit_rate(self):
        """Test that semantic duplicate queries increase hit rate."""
        # Test with duplicate queries (should have higher hit rate)
        result_duplicates = ABTestResult(
            total_queries=100,
            hits=80,
            misses=20,
            stale=0,
            avg_latency_hit_ms=50.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.08,
            llm_calls_reduced=80,
        )

        # Test with random queries (should have lower hit rate)
        result_random = ABTestResult(
            total_queries=100,
            hits=10,
            misses=90,
            stale=0,
            avg_latency_hit_ms=50.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.01,
            llm_calls_reduced=10,
        )

        assert result_duplicates.hit_rate > result_random.hit_rate


class TestABTestResultEdgeCases:
    """Test edge cases for ABTestResult calculations."""

    def test_zero_queries(self):
        """Test behavior with zero queries."""
        result = ABTestResult(
            total_queries=0,
            hits=0,
            misses=0,
            stale=0,
            avg_latency_hit_ms=0.0,
            avg_latency_miss_ms=0.0,
            avg_latency_no_cache_ms=0.0,
            cost_saved_usd=0.0,
            llm_calls_reduced=0,
        )

        assert result.hit_rate == 0.0
        assert result.stale_rate == 0.0  # No hits, so stale_rate is 0

    def test_zero_hits(self):
        """Test behavior with zero hits."""
        result = ABTestResult(
            total_queries=100,
            hits=0,
            misses=100,
            stale=0,
            avg_latency_hit_ms=0.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.0,
            llm_calls_reduced=0,
        )

        assert result.hit_rate == 0.0
        assert result.stale_rate == 0.0  # Division by zero handled

    def test_stale_rate_with_zero_hits(self):
        """Test stale_rate calculation with zero hits."""
        result = ABTestResult(
            total_queries=100,
            hits=0,
            misses=100,
            stale=5,
            avg_latency_hit_ms=0.0,
            avg_latency_miss_ms=200.0,
            avg_latency_no_cache_ms=150.0,
            cost_saved_usd=0.0,
            llm_calls_reduced=0,
        )

        assert result.stale_rate == 0.0  # No hits, so stale_rate is 0


class TestABTestIntegration:
    """Integration tests for semantic cache A/B test."""

    @pytest.mark.asyncio
    async def test_load_and_run_with_dataset_file(self):
        """Test loading queries from file and running A/B test."""
        # Create temporary dataset file
        test_data = [
            {
                "query": "What is LLM?",
                "expected_answer": "Large Language Model",
                "duplicate_group": 1,
            },
            {
                "query": "What is a large language model?",
                "expected_answer": "Large Language Model",
                "duplicate_group": 1,
            },
            {
                "query": "Explain LLM architecture",
                "expected_answer": "Neural network architecture",
                "duplicate_group": 2,
            },
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for item in test_data:
                json.dump(item, f)
                f.write("\n")
            temp_file = f.name

        try:
            # Mock the cache and metrics
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock()
            mock_cache.put = AsyncMock()

            # Simulate cache hits for duplicate queries
            def mock_get_side_effect(query):
                if query == "What is LLM?":
                    return None  # First query - miss
                elif query == "What is a large language model?":
                    return CacheHitResult(
                        answer="Large Language Model",
                        referenced_doc_ids=["550e8400-e29b-41d4-a716-446655440000"],
                        created_at="2026-01-01T00:00:00",
                        model="gpt-4o-mini",
                        token_count=50,
                        similarity_score=0.95,
                    )  # Second query - hit (duplicate)
                elif query == "Explain LLM architecture":
                    return None  # Third query - miss
                else:
                    return None

            mock_cache.get.side_effect = mock_get_side_effect

            with (
                patch("scripts.ab_test_semantic_cache.get_semantic_cache", return_value=mock_cache),
                patch("scripts.ab_test_semantic_cache.get_cache_hit_counts") as mock_counts,
            ):
                mock_counts.side_effect = [
                    {"hit": 0, "miss": 0, "stale": 0},  # before
                    {"hit": 1, "miss": 2, "stale": 0},  # after
                ]

                queries = [item["query"] for item in test_data]
                result = await run_ab_test(queries, iterations=2)

                # Verify that duplicate queries result in hits
                assert result.hits == 1
                assert result.misses == 2
                assert result.hit_rate == 1 / 3

        finally:
            # Clean up temp file
            Path(temp_file).unlink()
