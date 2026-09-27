"""RAG evaluator for quality metrics and A/B testing."""

import json
import time
from typing import Any

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.eval.mock_pipeline import MockRetrievalPipeline
from llm_client.rag.eval.models import CategoryReport, EvalReport, QueryResult


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
        """Load evaluation dataset from JSONL file."""
        dataset = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    dataset.append(json.loads(line))
        return dataset
    
    async def evaluate(self, config: RetrieverConfig) -> EvalReport:
        """Evaluate RAG pipeline with given configuration.
        
        Args:
            config: RetrieverConfig to test
            
        Returns:
            EvalReport with recall@5 and per-category metrics
        """
        query_results = []
        category_results = {}
        
        # Initialize category tracking
        for entry in self.dataset:
            category = entry["category"]
            if category not in category_results:
                category_results[category] = []
        
        # Evaluate each query
        for entry in self.dataset:
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
                relevant_docs=[doc for doc in self.pipeline.corpus 
                             if doc["id"] in relevant_doc_ids]
            )
            query_results.append(query_result)
            category_results[category].append(query_result)
        
        # Calculate overall metrics
        total_queries = len(query_results)
        recall_at_5 = sum(1 for qr in query_results if qr.hit_at_5) / total_queries
        avg_latency_ms = sum(qr.latency_ms for qr in query_results) / total_queries
        
        # Calculate per-category metrics
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
                query_results=results
            )
        
        return EvalReport(
            recall_at_5=recall_at_5,
            avg_latency_ms=avg_latency_ms,
            per_category=per_category,
            query_results=query_results
        )
    
    async def ab_test(self, baseline_config: RetrieverConfig, 
                     treatment_config: RetrieverConfig) -> dict[str, Any]:
        """Run A/B test comparing baseline and treatment configurations.
        
        Args:
            baseline_config: Configuration without reranker (baseline)
            treatment_config: Configuration with reranker (treatment)
            
        Returns:
            Dictionary with A/B test results
        """
        # Evaluate both configurations
        baseline_report = await self.evaluate(baseline_config)
        treatment_report = await self.evaluate(treatment_config)
        
        # Calculate improvement
        improvement = (treatment_report.recall_at_5 - baseline_report.recall_at_5) / \
                    baseline_report.recall_at_5 * 100
        latency_overhead = treatment_report.avg_latency_ms - baseline_report.avg_latency_ms
        
        # Determine pass/fail
        passes = improvement >= 15.0 and latency_overhead < 100.0
        
        return {
            "baseline": {
                "recall_at_5": baseline_report.recall_at_5,
                "avg_latency_ms": baseline_report.avg_latency_ms,
                "per_category": {
                    cat: {
                        "recall_at_5": report.recall_at_5,
                        "avg_latency_ms": report.avg_latency_ms
                    }
                    for cat, report in baseline_report.per_category.items()
                }
            },
            "treatment": {
                "recall_at_5": treatment_report.recall_at_5,
                "avg_latency_ms": treatment_report.avg_latency_ms,
                "per_category": {
                    cat: {
                        "recall_at_5": report.recall_at_5,
                        "avg_latency_ms": report.avg_latency_ms
                    }
                    for cat, report in treatment_report.per_category.items()
                }
            },
            "improvement_percent": improvement,
            "latency_overhead_ms": latency_overhead,
            "passes": passes,
            "criteria": {
                "recall_improvement_threshold": 15.0,
                "latency_threshold_ms": 100.0,
                "actual_improvement": improvement,
                "actual_latency": latency_overhead
            }
        }