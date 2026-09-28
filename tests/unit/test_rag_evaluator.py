"""Unit tests for RAG evaluator functionality."""

from unittest.mock import AsyncMock, patch

import pytest

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.eval.mock_pipeline import MockRetrievalPipeline
from llm_client.rag.eval.models import EvalReport


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
def mock_pipeline(sample_corpus):
    """Mock retrieval pipeline."""
    with patch('llm_client.rag.eval.evaluator.MockRetrievalPipeline') as mock:
        pipeline = MockRetrievalPipeline(sample_corpus)
        
        # Mock search method to return predictable results
        async def mock_search(query, config):
            if "redis" in query:
                return [{"id": "doc_1", "score": 0.9, "content": "Redis config", "metadata": {}}]
            elif "docker" in query:
                return [{"id": "doc_2", "score": 0.8, "content": "Docker setup", "metadata": {}}]
            elif "python" in query:
                return [{"id": "doc_3", "score": 0.7, "content": "Python async", "metadata": {}}]
            else:
                return []
        
        pipeline.search = AsyncMock(side_effect=mock_search)
        mock.return_value = pipeline
        yield pipeline


@pytest.fixture
def evaluator(sample_dataset, sample_corpus):
    """Evaluator fixture."""
    with patch('llm_client.rag.eval.evaluator.MockRetrievalPipeline') as mock:
        pipeline = MockRetrievalPipeline(sample_corpus)
        mock.return_value = pipeline
        
        return RAGEEvaluator("mock_dataset.jsonl", sample_corpus)


class TestRAGEvaluator:
    """Test cases for RAGEvaluator class."""
    
    def test_init(self, evaluator, sample_dataset, sample_corpus):
        """Test evaluator initialization."""
        assert evaluator.eval_dataset_path == "mock_dataset.jsonl"
        assert evaluator.dataset == sample_dataset
        assert isinstance(evaluator.pipeline, MockRetrievalPipeline)
    
    def test_load_dataset(self, evaluator):
        """Test dataset loading."""
        # Mock file reading
        with patch('builtins.open', mock_open_read(sample_dataset)):
            dataset = evaluator._load_dataset("test.jsonl")
            assert len(dataset) == 3
            assert dataset[0]["query"] == "redis config"
            assert dataset[0]["category"] == "exact_term"
    
    @pytest.mark.asyncio
    async def test_evaluate_with_hit(self, evaluator):
        """Test evaluation with successful recall@5."""
        config = RetrieverConfig(reranker_enabled=False)
        
        # Mock pipeline to return relevant document
        async def mock_search(query, config):
            if query == "redis config":
                return [{"id": "doc_1", "score": 0.9, "content": "Redis config", "metadata": {}}]
            return []
        
        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)
        
        result = await evaluator.evaluate(config)
        
        assert isinstance(result, EvalReport)
        assert result.recall_at_5 == 1.0  # One query, one hit
        assert "exact_term" in result.per_category
        assert result.per_category["exact_term"].recall_at_5 == 1.0
        assert len(result.query_results) == 1
        assert result.query_results[0].hit_at_5 is True
    
    @pytest.mark.asyncio
    async def test_evaluate_with_miss(self, evaluator):
        """Test evaluation with no recall@5."""
        config = RetrieverConfig(reranker_enabled=False)
        
        # Mock pipeline to return irrelevant document
        async def mock_search(query, config):
            return [{"id": "doc_99", "score": 0.5, "content": "Irrelevant content", "metadata": {}}]
        
        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)
        
        result = await evaluator.evaluate(config)
        
        assert isinstance(result, EvalReport)
        assert result.recall_at_5 == 0.0  # One query, no hit
        assert result.per_category["exact_term"].recall_at_5 == 0.0
        assert len(result.query_results) == 1
        assert result.query_results[0].hit_at_5 is False
    
    @pytest.mark.asyncio
    async def test_evaluate_multiple_queries(self, evaluator):
        """Test evaluation with multiple queries."""
        config = RetrieverConfig(reranker_enabled=False)
        
        # Mock pipeline to return relevant docs for some queries
        async def mock_search(query, config):
            if "redis" in query or "docker" in query:
                return [{"id": "doc_1", "score": 0.9, "content": "Relevant content", "metadata": {}}]
            return []
        
        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)
        
        result = await evaluator.evaluate(config)
        
        # Should have 3 queries (from sample_dataset)
        assert len(result.query_results) == 3
        # Should have 2 hits (redis and docker)
        hits = sum(1 for qr in result.query_results if qr.hit_at_5)
        assert hits == 2
        assert result.recall_at_5 == 2/3
    
    @pytest.mark.asyncio
    async def test_ab_test(self, evaluator):
        """Test A/B test comparison."""
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)
        
        # Mock pipeline to return different results for baseline vs treatment
        async def mock_search(query, config):
            if config.reranker_enabled:
                # Treatment returns better results
                return [{"id": "doc_1", "score": 0.95, "content": "High quality result", "metadata": {}}]
            else:
                # Baseline returns worse results
                return [{"id": "doc_99", "score": 0.5, "content": "Low quality result", "metadata": {}}]
        
        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)
        
        results = await evaluator.ab_test(baseline_config, treatment_config)
        
        assert "baseline" in results
        assert "treatment" in results
        assert "improvement_percent" in results
        assert "passes" in results
        assert "criteria" in results
        
        # Check that improvement is calculated correctly
        baseline_recall = results["baseline"]["recall_at_5"]
        treatment_recall = results["treatment"]["recall_at_5"]
        expected_improvement = (treatment_recall - baseline_recall) / baseline_recall * 100
        assert results["improvement_percent"] == expected_improvement
    
    @pytest.mark.asyncio
    async def test_ab_test_pass_criteria(self, evaluator):
        """Test A/B test pass/fail criteria."""
        baseline_config = RetrieverConfig(reranker_enabled=False)
        treatment_config = RetrieverConfig(reranker_enabled=True)
        
        # Mock results that meet criteria
        async def mock_search(query, config):
            # Simulate improvement from 0.4 to 0.6 (50% improvement > 15%)
            # and latency overhead < 100ms
            if config.reranker_enabled:
                return [{"id": "doc_1", "score": 0.95, "content": "Good result", "metadata": {}, "latency_ms": 150}]
            else:
                return [{"id": "doc_99", "score": 0.5, "content": "Bad result", "metadata": {}, "latency_ms": 50}]
        
        evaluator.pipeline.search = AsyncMock(side_effect=mock_search)
        
        results = await evaluator.ab_test(baseline_config, treatment_config)
        
        # Should pass based on improvement and latency
        assert results["improvement_percent"] > 15.0
        assert results["latency_overhead_ms"] < 100.0
        assert results["passes"] is True


def mock_open_read(data):
    """Mock open function for reading test data."""
    from unittest.mock import mock_open
    
    def mock_open_func(filename, mode='r', **kwargs):
        if 'test.jsonl' in filename:
            return mock_open(read_data='\n'.join([str(item) for item in data]))()
        return mock_open()()
    
    return mock_open_func


class TestEvalReport:
    """Test cases for EvalReport dataclass."""
    
    def test_to_dict(self):
        """Test EvalReport to_dict conversion."""
        from llm_client.rag.eval.models import CategoryReport, QueryResult
        
        # Create sample data
        query_result = QueryResult(
            query="test query",
            category="test_category",
            retrieved_ids=["doc_1"],
            relevant_ids=["doc_1"],
            hit_at_5=True,
            latency_ms=100.0
        )
        
        category_report = CategoryReport(
            category="test_category",
            query_count=1,
            recall_at_5=1.0,
            avg_latency_ms=100.0,
            query_results=[query_result]
        )
        
        eval_report = EvalReport(
            recall_at_5=1.0,
            avg_latency_ms=100.0,
            per_category={"test_category": category_report},
            query_results=[query_result]
        )
        
        # Convert to dict
        report_dict = eval_report.to_dict()
        
        # Check structure
        assert "recall_at_5" in report_dict
        assert "avg_latency_ms" in report_dict
        assert "per_category" in report_dict
        assert "query_results" in report_dict
        assert "timestamp" in report_dict
        
        # Check values
        assert report_dict["recall_at_5"] == 1.0
        assert report_dict["avg_latency_ms"] == 100.0
        assert len(report_dict["query_results"]) == 1
        assert report_dict["query_results"][0]["hit_at_5"] is True
        assert report_dict["per_category"]["test_category"]["recall_at_5"] == 1.0