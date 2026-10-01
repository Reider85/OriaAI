"""Unit tests for RAG evaluator functionality."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.eval.evaluator import RAGEvaluator
from llm_client.rag.eval.mock_pipeline import MockRetrievalPipeline
from llm_client.rag.eval.models import CategoryReport, EvalReport, QueryResult

pytestmark = pytest.mark.eval


@pytest.fixture
def sample_corpus():
    """Sample document corpus for testing."""
    return [
        {"id": "doc_1", "content": "Redis connection configuration", "metadata": {"source": "redis"}},
        {"id": "doc_2", "content": "Docker Compose setup", "metadata": {"source": "docker"}},
        {"id": "doc_3", "content": "Python async patterns", "metadata": {"source": "python"}},
        {"id": "doc_4", "content": "PostgreSQL database", "metadata": {"source": "postgres"}},
        {"id": "doc_5", "content": "Prometheus monitoring", "metadata": {"source": "prometheus"}},
    ]


@pytest.fixture
def sample_dataset():
    """Sample evaluation dataset for testing."""
    return [
        {"query": "redis config", "relevant_doc_ids": ["doc_1"], "category": "exact_term"},
        {"query": "docker setup", "relevant_doc_ids": ["doc_2"], "category": "semantic"},
        {"query": "python async", "relevant_doc_ids": ["doc_3"], "category": "fuzzy"},
    ]


@pytest.fixture
def dataset_file(tmp_path: Path, sample_dataset):
    """Create a temporary dataset file for testing."""
    dataset_path = tmp_path / "test_dataset.jsonl"
    with open(dataset_path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(item) + "\n" for item in sample_dataset)
    return str(dataset_path)


class TestRAGEvaluator:
    """Test cases for RAGEvaluator class."""

    def test_init(self, dataset_file, sample_corpus):
        """Test evaluator initialization."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        assert evaluator.eval_dataset_path == dataset_file
        assert len(evaluator.dataset) == 3
        assert evaluator.dataset[0]["query"] == "redis config"
        assert evaluator.dataset[0]["category"] == "exact_term"
        assert isinstance(evaluator.pipeline, MockRetrievalPipeline)

    def test_load_dataset(self, dataset_file, sample_corpus):
        """Test dataset loading."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        dataset = evaluator._load_dataset(dataset_file)
        assert len(dataset) == 3
        assert dataset[0]["query"] == "redis config"
        assert dataset[0]["category"] == "exact_term"
        assert dataset[0]["relevant_doc_ids"] == ["doc_1"]

    def test_validate_entry_valid(self):
        """Test validation of valid dataset entry."""
        entry = {"query": "test query", "category": "exact_term", "relevant_doc_ids": ["doc_1"]}
        RAGEvaluator._validate_entry(entry, "test.jsonl", 1)

    def test_validate_entry_non_dict(self):
        """Test validation raises TypeError for non-dict entry."""
        with pytest.raises(TypeError, match="entry must be a JSON object"):
            RAGEvaluator._validate_entry("not a dict", "test.jsonl", 1)

    def test_validate_entry_missing_query(self):
        """Test validation raises ValueError for missing query field."""
        entry = {"category": "exact_term", "relevant_doc_ids": ["doc_1"]}
        with pytest.raises(ValueError, match="'query' must be a non-empty string"):
            RAGEvaluator._validate_entry(entry, "test.jsonl", 1)

    def test_validate_entry_empty_query(self):
        """Test validation raises ValueError for empty query field."""
        entry = {"query": "", "category": "exact_term", "relevant_doc_ids": ["doc_1"]}
        with pytest.raises(ValueError, match="'query' must be a non-empty string"):
            RAGEvaluator._validate_entry(entry, "test.jsonl", 1)

    def test_validate_entry_invalid_category(self):
        """Test validation raises ValueError for invalid category field."""
        entry = {"query": "test query", "category": 123, "relevant_doc_ids": ["doc_1"]}
        with pytest.raises(ValueError, match="'category' must be a non-empty string"):
            RAGEvaluator._validate_entry(entry, "test.jsonl", 1)

    def test_validate_entry_missing_relevant_doc_ids(self):
        """Test validation raises ValueError for missing relevant_doc_ids field."""
        entry = {"query": "test query", "category": "exact_term"}
        with pytest.raises(ValueError, match="'relevant_doc_ids' must be a non-empty list"):
            RAGEvaluator._validate_entry(entry, "test.jsonl", 1)

    def test_validate_entry_invalid_relevant_doc_ids(self):
        """Test validation raises ValueError for invalid relevant_doc_ids field."""
        entry = {"query": "test query", "category": "exact_term", "relevant_doc_ids": ["doc_1", 123]}
        with pytest.raises(ValueError, match="'relevant_doc_ids' must contain non-empty strings"):
            RAGEvaluator._validate_entry(entry, "test.jsonl", 1)

    def test_validate_entry_empty_relevant_doc_ids(self):
        """Test validation raises ValueError for empty relevant_doc_ids field."""
        entry = {"query": "test query", "category": "exact_term", "relevant_doc_ids": []}
        with pytest.raises(ValueError, match="'relevant_doc_ids' must be a non-empty list"):
            RAGEvaluator._validate_entry(entry, "test.jsonl", 1)

    @pytest.mark.asyncio
    async def test_evaluate_with_hit(self, dataset_file, sample_corpus):
        """Test evaluation with successful recall@5."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        config = RetrieverConfig(reranker_enabled=False)

        async def mock_search(query, config):
            if query == "redis config":
                return [{"id": "doc_1", "score": 0.9, "content": "Redis config", "metadata": {}}]
            elif query == "docker setup":
                return [{"id": "doc_2", "score": 0.8, "content": "Docker setup", "metadata": {}}]
            elif query == "python async":
                return [{"id": "doc_3", "score": 0.7, "content": "Python async", "metadata": {}}]
            return []

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        result = await evaluator.evaluate(config)

        assert isinstance(result, EvalReport)
        assert result.recall_at_5 == 1.0
        assert "exact_term" in result.per_category
        assert result.per_category["exact_term"].recall_at_5 == 1.0
        assert len(result.query_results) == 3
        assert all(qr.hit_at_5 for qr in result.query_results)

    @pytest.mark.asyncio
    async def test_evaluate_with_miss(self, dataset_file, sample_corpus):
        """Test evaluation with no recall@5."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        config = RetrieverConfig(reranker_enabled=False)

        async def mock_search(query, config):
            return [{"id": "doc_99", "score": 0.5, "content": "Irrelevant content", "metadata": {}}]

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        result = await evaluator.evaluate(config)

        assert isinstance(result, EvalReport)
        assert result.recall_at_5 == 0.0
        assert result.per_category["exact_term"].recall_at_5 == 0.0
        assert len(result.query_results) == 3
        assert all(not qr.hit_at_5 for qr in result.query_results)

    @pytest.mark.asyncio
    async def test_evaluate_multiple_queries(self, dataset_file, sample_corpus):
        """Test evaluation with multiple queries."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        config = RetrieverConfig(reranker_enabled=False)

        async def mock_search(query, config):
            if "redis" in query:
                return [{"id": "doc_1", "score": 0.9, "content": "Relevant content", "metadata": {}}]
            elif "docker" in query:
                return [{"id": "doc_2", "score": 0.9, "content": "Relevant content", "metadata": {}}]
            return []

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        result = await evaluator.evaluate(config)

        assert len(result.query_results) == 3
        hits = sum(1 for qr in result.query_results if qr.hit_at_5)
        assert hits == 2
        assert result.recall_at_5 == 2 / 3
        assert result.per_category["exact_term"].recall_at_5 == 1.0
        assert result.per_category["semantic"].recall_at_5 == 1.0
        assert result.per_category["fuzzy"].recall_at_5 == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_with_limit(self, dataset_file, sample_corpus):
        """Test evaluation with query limit."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        config = RetrieverConfig(reranker_enabled=False)

        async def mock_search(query, config):
            return [{"id": "doc_1", "score": 0.9, "content": "Relevant content", "metadata": {}}]

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        result = await evaluator.evaluate(config, limit=1)

        assert len(result.query_results) == 1
        assert result.recall_at_5 == 1.0
        assert result.query_results[0].query == "redis config"

    @pytest.mark.asyncio
    async def test_evaluate_zero_baseline(self, dataset_file, sample_corpus):
        """Test evaluation when baseline recall is zero."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        config = RetrieverConfig(reranker_enabled=False)

        async def mock_search(query, config):
            return [{"id": "doc_99", "score": 0.5, "content": "Irrelevant content", "metadata": {}}]

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        result = await evaluator.evaluate(config)

        assert result.recall_at_5 == 0.0
        assert result.per_category["exact_term"].recall_at_5 == 0.0
        assert result.per_category["semantic"].recall_at_5 == 0.0
        assert result.per_category["fuzzy"].recall_at_5 == 0.0

    @pytest.mark.asyncio
    async def test_ab_test_improvement(self, dataset_file, sample_corpus):
        """Test A/B test with improvement."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        async def mock_search(query, config):
            if config.reranker_enabled:
                if query == "redis config":
                    return [{"id": "doc_1", "score": 0.95, "content": "High quality result", "metadata": {}}]
                elif query == "docker setup":
                    return [{"id": "doc_2", "score": 0.95, "content": "High quality result", "metadata": {}}]
                elif query == "python async":
                    return [{"id": "doc_3", "score": 0.95, "content": "High quality result", "metadata": {}}]
            else:
                if query == "redis config":
                    return [{"id": "doc_1", "score": 0.6, "content": "Low quality result", "metadata": {}}]
                elif query == "docker setup" or query == "python async":
                    return [{"id": "doc_99", "score": 0.5, "content": "Low quality result", "metadata": {}}]
            return []

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        assert "baseline" in results
        assert "treatment" in results
        assert "improvement_percent" in results
        assert "passes" in results
        assert "criteria" in results

        baseline_recall = results["baseline"]["recall_at_5"]
        treatment_recall = results["treatment"]["recall_at_5"]
        expected_improvement = (treatment_recall - baseline_recall) / baseline_recall * 100
        assert results["improvement_percent"] == expected_improvement

    @pytest.mark.asyncio
    async def test_ab_test_zero_baseline(self, dataset_file, sample_corpus):
        """Test A/B test when baseline recall is zero."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        async def mock_search(query, config):
            if config.reranker_enabled:
                if query == "redis config":
                    return [{"id": "doc_1", "score": 0.95, "content": "High quality result", "metadata": {}}]
                elif query == "docker setup":
                    return [{"id": "doc_2", "score": 0.95, "content": "High quality result", "metadata": {}}]
                elif query == "python async":
                    return [{"id": "doc_3", "score": 0.95, "content": "High quality result", "metadata": {}}]
            else:
                return []
            return []

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        assert results["baseline"]["recall_at_5"] == 0.0
        assert results["treatment"]["recall_at_5"] == 1.0
        assert results["improvement_percent"] is None
        assert results["passes"] is True

    @pytest.mark.asyncio
    async def test_ab_test_no_improvement(self, dataset_file, sample_corpus):
        """Test A/B test when there's no improvement."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        async def mock_search(query, config):
            return [{"id": "doc_1", "score": 0.9, "content": "Same result", "metadata": {}}]

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        assert results["improvement_percent"] == 0.0
        assert results["passes"] is False

    @pytest.mark.asyncio
    async def test_ab_test_pass_criteria(self, dataset_file, sample_corpus):
        """Test A/B test pass/fail criteria."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        async def mock_search(query, config):
            if config.reranker_enabled:
                if query == "redis config":
                    return [{"id": "doc_1", "score": 0.95, "content": "Good result", "metadata": {}}]
                elif query == "docker setup":
                    return [{"id": "doc_2", "score": 0.95, "content": "Good result", "metadata": {}}]
                elif query == "python async":
                    return [{"id": "doc_3", "score": 0.95, "content": "Good result", "metadata": {}}]
            else:
                if query == "redis config":
                    return [{"id": "doc_1", "score": 0.6, "content": "Bad result", "metadata": {}}]
                elif query == "docker setup" or query == "python async":
                    return [{"id": "doc_99", "score": 0.5, "content": "Bad result", "metadata": {}}]
            return []

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        assert results["improvement_percent"] > 15.0
        assert results["latency_overhead_ms"] < 100.0
        assert results["passes"] is True

    @pytest.mark.asyncio
    async def test_ab_test_fail_latency(self, dataset_file, sample_corpus):
        """Test A/B test fails due to high latency."""
        import asyncio

        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        async def mock_search(query, config):
            if config.reranker_enabled:
                # Simulate high latency for treatment
                await asyncio.sleep(0.2)
                if query == "redis config":
                    return [{"id": "doc_1", "score": 0.95, "content": "Good result", "metadata": {}}]
                elif query == "docker setup":
                    return [{"id": "doc_2", "score": 0.95, "content": "Good result", "metadata": {}}]
                elif query == "python async":
                    return [{"id": "doc_3", "score": 0.95, "content": "Good result", "metadata": {}}]
            else:
                if query == "redis config":
                    return [{"id": "doc_1", "score": 0.6, "content": "Bad result", "metadata": {}}]
                elif query == "docker setup" or query == "python async":
                    return [{"id": "doc_99", "score": 0.5, "content": "Bad result", "metadata": {}}]
            return []

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        assert results["improvement_percent"] > 15.0
        assert results["latency_overhead_ms"] > 100.0
        assert results["passes"] is False

    @pytest.mark.asyncio
    async def test_ab_test_per_category(self, dataset_file, sample_corpus):
        """Test A/B test per-category breakdown."""
        evaluator = RAGEvaluator(dataset_file, sample_corpus)
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)

        async def mock_search(query, config):
            if config.reranker_enabled:
                if "redis" in query:
                    return [{"id": "doc_1", "score": 0.95, "content": "Excellent redis config", "metadata": {}}]
                elif "docker" in query:
                    return [{"id": "doc_2", "score": 0.95, "content": "Excellent docker setup", "metadata": {}}]
                elif "python" in query:
                    return [{"id": "doc_3", "score": 0.95, "content": "Excellent python async", "metadata": {}}]
            else:
                if "redis" in query:
                    return [{"id": "doc_1", "score": 0.9, "content": "Good redis config", "metadata": {}}]
                elif "docker" in query:
                    return [{"id": "doc_99", "score": 0.5, "content": "Bad docker setup", "metadata": {}}]
                elif "python" in query:
                    return [{"id": "doc_99", "score": 0.5, "content": "Bad python async", "metadata": {}}]

        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)

        results = await evaluator.ab_test(baseline_config, treatment_config)

        assert "per_category" in results["baseline"]
        assert "per_category" in results["treatment"]

        exact_term_baseline = results["baseline"]["per_category"]["exact_term"]["recall_at_5"]
        exact_term_treatment = results["treatment"]["per_category"]["exact_term"]["recall_at_5"]
        assert exact_term_baseline == 1.0
        assert exact_term_treatment == 1.0

        semantic_baseline = results["baseline"]["per_category"]["semantic"]["recall_at_5"]
        semantic_treatment = results["treatment"]["per_category"]["semantic"]["recall_at_5"]
        assert semantic_baseline == 0.0
        assert semantic_treatment == 1.0

        fuzzy_baseline = results["baseline"]["per_category"]["fuzzy"]["recall_at_5"]
        fuzzy_treatment = results["treatment"]["per_category"]["fuzzy"]["recall_at_5"]
        assert fuzzy_baseline == 0.0
        assert fuzzy_treatment == 1.0


class TestEvalReport:
    """Test cases for EvalReport dataclass."""

    def test_to_dict(self):
        """Test EvalReport to_dict conversion."""
        query_result = QueryResult(
            query="test query",
            category="test_category",
            retrieved_ids=["doc_1"],
            relevant_ids=["doc_1"],
            hit_at_5=True,
            latency_ms=100.0,
        )

        category_report = CategoryReport(
            category="test_category",
            query_count=1,
            recall_at_5=1.0,
            avg_latency_ms=100.0,
            query_results=[query_result],
        )

        eval_report = EvalReport(
            recall_at_5=1.0,
            avg_latency_ms=100.0,
            per_category={"test_category": category_report},
            query_results=[query_result],
        )

        report_dict = eval_report.to_dict()

        assert "recall_at_5" in report_dict
        assert "avg_latency_ms" in report_dict
        assert "per_category" in report_dict
        assert "query_results" in report_dict
        assert "timestamp" in report_dict

        assert report_dict["recall_at_5"] == 1.0
        assert report_dict["avg_latency_ms"] == 100.0
        assert len(report_dict["query_results"]) == 1
        assert report_dict["query_results"][0]["hit_at_5"] is True
        assert report_dict["per_category"]["test_category"]["recall_at_5"] == 1.0
