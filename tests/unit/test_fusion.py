"""Unit tests for RRF fusion functionality."""


import pytest

from llm_client.rag.retrieval.fusion import (
    FusionMetrics,
    NullFusionMetrics,
    rrf_fusion,
    rrf_fusion_with_metrics,
)


class TestRRFFusion:
    """Test cases for the rrf_fusion function."""

    def test_empty_lists(self):
        """Test fusion with empty input lists."""
        result = rrf_fusion([], [])
        assert result == []

    def test_one_list_empty(self):
        """Test fusion with one empty list."""
        vector_docs = [
            {"id": "doc1", "content": "Content 1"},
            {"id": "doc2", "content": "Content 2"},
        ]
        result = rrf_fusion(vector_docs, [])
        assert len(result) == 2
        assert result[0]["id"] == "doc1"
        assert result[1]["id"] == "doc2"

    def test_full_overlap(self):
        """Test fusion with identical documents in both lists."""
        doc = {"id": "doc1", "content": "Content 1"}
        vector_docs = [doc, {"id": "doc2", "content": "Content 2"}]
        bm25_docs = [doc, {"id": "doc2", "content": "Content 2"}]
        
        result = rrf_fusion(vector_docs, bm25_docs)
        
        # Should have 2 unique docs
        assert len(result) == 2
        
        # Doc1 should have higher score (found in both retrievers)
        assert result[0]["id"] == "doc1"
        assert result[0]["rrf_score"] > result[1]["rrf_score"]
        
        # Both should have rrf_score field
        assert "rrf_score" in result[0]
        assert "rrf_score" in result[1]

    def test_no_overlap(self):
        """Test fusion with no overlapping documents."""
        vector_docs = [
            {"id": "doc1", "content": "Content 1"},
            {"id": "doc2", "content": "Content 2"},
        ]
        bm25_docs = [
            {"id": "doc3", "content": "Content 3"},
            {"id": "doc4", "content": "Content 4"},
        ]
        
        result = rrf_fusion(vector_docs, bm25_docs, top_k=4)
        
        # Should have 4 unique docs
        assert len(result) == 4
        
        # All should have rrf_score field
        for doc in result:
            assert "rrf_score" in doc

    def test_partial_overlap(self):
        """Test fusion with partial document overlap."""
        vector_docs = [
            {"id": "doc1", "content": "Content 1"},
            {"id": "doc2", "content": "Content 2"},
            {"id": "doc3", "content": "Content 3"},
        ]
        bm25_docs = [
            {"id": "doc2", "content": "Content 2"},
            {"id": "doc4", "content": "Content 4"},
            {"id": "doc5", "content": "Content 5"},
        ]
        
        result = rrf_fusion(vector_docs, bm25_docs, top_k=5)
        
        # Should have 5 unique docs (3 + 3 - 1 overlap)
        assert len(result) == 5
        
        # Doc2 should have highest score (found in both)
        assert result[0]["id"] == "doc2"
        assert "rrf_score" in result[0]

    def test_weights_boost_bm25(self):
        """Test that bm25_weight=0.7 shifts ranking toward BM25 hits."""
        vector_docs = [
            {"id": "doc1", "content": "Content 1"},
            {"id": "doc2", "content": "Content 2"},
        ]
        bm25_docs = [
            {"id": "doc3", "content": "Content 3"},
            {"id": "doc4", "content": "Content 4"},
        ]
        
        # With BM25 weight higher, BM25 docs should rank higher
        result_balanced = rrf_fusion(vector_docs, bm25_docs, vector_weight=0.5, bm25_weight=0.5)
        result_bm25_favored = rrf_fusion(vector_docs, bm25_docs, vector_weight=0.3, bm25_weight=0.7)
        
        # Doc3 and doc4 (BM25) should rank higher when bm25_weight is higher
        bm25_ids_favored = {doc["id"] for doc in result_bm25_favored[:2]}
        vector_ids_favored = {doc["id"] for doc in result_balanced[:2]}
        
        # BM25 docs should appear earlier when weight is higher
        assert "doc3" in bm25_ids_favored
        assert "doc4" in bm25_ids_favored

    def test_k_constant_parameter(self):
        """Test that k_constant affects scoring correctly."""
        doc = {"id": "doc1", "content": "Content 1"}
        
        # With different k constants, scores should differ
        result_k60 = rrf_fusion([doc], [doc], k_constant=60)
        result_k10 = rrf_fusion([doc], [doc], k_constant=10)
        
        # Lower k should give higher score
        assert result_k10[0]["rrf_score"] > result_k60[0]["rrf_score"]

    def test_top_k_limiting(self):
        """Test that top_k correctly limits output size."""
        vector_docs = [{"id": f"doc{i}", "content": f"Content {i}"} for i in range(1, 6)]
        bm25_docs = [{"id": f"doc{i}", "content": f"Content {i}"} for i in range(6, 11)]
        
        result = rrf_fusion(vector_docs, bm25_docs, top_k=3)
        assert len(result) == 3

    def test_idempotent_operation(self):
        """Test that operation is idempotent (same input gives same output)."""
        docs = [
            {"id": "doc1", "content": "Content 1"},
            {"id": "doc2", "content": "Content 2"},
        ]
        
        result1 = rrf_fusion(docs, docs)
        result2 = rrf_fusion(docs, docs)
        
        # Results should be identical
        assert result1 == result2
        
        # Each doc should have score from both retrievers
        # Doc1 appears at rank 1 in both lists: score = 1.0/(60+1)
        # Doc2 appears at rank 2 in both lists: score = 1.0/(60+2)
        expected_score_doc1 = 1.0 / (60 + 1)
        expected_score_doc2 = 1.0 / (60 + 2)
        
        # Sort by ID to ensure consistent ordering
        result1_sorted = sorted(result1, key=lambda x: x["id"])
        result2_sorted = sorted(result2, key=lambda x: x["id"])
        
        assert result1_sorted[0]["id"] == "doc1"
        assert result1_sorted[1]["id"] == "doc2"
        assert result1_sorted[0]["rrf_score"] == expected_score_doc1
        assert result1_sorted[1]["rrf_score"] == expected_score_doc2

    def test_latency_performance(self):
        """Test that fusion is fast enough for typical workloads."""
        # Create 40 documents (20 + 20)
        vector_docs = [{"id": f"vec_doc{i}", "content": f"Content {i}"} for i in range(20)]
        bm25_docs = [{"id": f"bm25_doc{i}", "content": f"Content {i}"} for i in range(20)]
        
        import time
        start = time.time()
        result = rrf_fusion(vector_docs, bm25_docs)
        latency_ms = (time.time() - start) * 1000
        
        assert len(result) == 40  # No overlap, all unique
        assert latency_ms < 5  # Should be very fast (<5ms)

    def test_document_id_fallback(self):
        """Test handling of missing document IDs."""
        vector_docs = [
            {"content": "Content 1"},  # No ID
            {"id": "doc2", "content": "Content 2"},
        ]
        bm25_docs = [
            {"content": "Content 3"},  # No ID  
            {"id": "doc4", "content": "Content 4"},
        ]
        
        result = rrf_fusion(vector_docs, bm25_docs)
        
        # Should have 4 documents with fallback IDs
        assert len(result) == 4
        assert any(doc["id"] == "vector_1" for doc in result)  # Fallback for first vector doc
        assert any(doc["id"] == "bm25_1" for doc in result)  # Fallback for first bm25 doc

    def test_validation_errors(self):
        """Test input validation raises appropriate errors."""
        # Invalid weights
        with pytest.raises(ValueError, match="between 0 and 1"):
            rrf_fusion([], [], vector_weight=1.5)
        
        with pytest.raises(ValueError, match="between 0 and 1"):
            rrf_fusion([], [], bm25_weight=-0.1)
        
        # Weights don't sum to 1.0
        with pytest.raises(ValueError, match="must equal 1.0"):
            rrf_fusion([], [], vector_weight=0.6, bm25_weight=0.6)


class TestFusionMetrics:
    """Test cases for FusionMetrics class."""

    def test_metrics_initialization(self):
        """Test that metrics initialize correctly."""
        metrics = FusionMetrics()
        assert metrics.prefix == "llm_client_rag_fusion"
        
        # Custom prefix
        metrics_custom = FusionMetrics(prefix="custom")
        assert metrics_custom.prefix == "custom"

    def test_null_metrics(self):
        """Test that NullFusionMetrics does nothing."""
        metrics = NullFusionMetrics()
        
        # Should not raise errors
        metrics.record_latency(10.0)
        metrics.set_input_count(5)
        metrics.set_output_count(3)
        metrics.set_overlap_count(1)
        metrics.reset()

    def test_metrics_recording(self):
        """Test that metrics record values correctly."""
        registry = None  # Use default registry
        metrics = FusionMetrics(registry=registry)
        
        # Record some values
        metrics.set_input_count(40)
        metrics.set_output_count(25)
        metrics.set_overlap_count(5)
        metrics.record_latency(12.5)
        
        # Values should be recorded (can't easily verify Prometheus values in unit tests)
        # But at least it shouldn't raise errors

    def test_metrics_reset(self):
        """Test that metrics reset correctly."""
        metrics = FusionMetrics()
        
        # Set some values
        metrics.set_input_count(10)
        metrics.set_output_count(5)
        
        # Reset should not raise errors
        metrics.reset()


class TestRRFFusionWithMetrics:
    """Test cases for rrf_fusion_with_metrics wrapper."""

    def test_wrapper_functionality(self):
        """Test that the wrapper correctly calls core function and records metrics."""
        vector_docs = [
            {"id": "doc1", "content": "Content 1"},
            {"id": "doc2", "content": "Content 2"},
        ]
        bm25_docs = [
            {"id": "doc3", "content": "Content 3"},
            {"id": "doc4", "content": "Content 4"},
        ]
        
        # Use null metrics to avoid Prometheus interference
        metrics = NullFusionMetrics()
        result = rrf_fusion_with_metrics(vector_docs, bm25_docs, metrics=metrics)
        
        # Should return fused documents
        assert len(result) == 4
        
        # All should have rrf_score
        for doc in result:
            assert "rrf_score" in doc

    def test_wrapper_error_handling(self):
        """Test that wrapper handles errors and records metrics."""
        vector_docs = [{"id": "doc1", "content": "Content 1"}]
        bm25_docs = [{"id": "doc2", "content": "Content 2"}]
        
        # Use null metrics
        metrics = NullFusionMetrics()
        
        # This should work fine, but let's test with invalid weights to trigger error
        with pytest.raises(ValueError):
            rrf_fusion_with_metrics(
                vector_docs, 
                bm25_docs, 
                vector_weight=1.5,  # Invalid weight
                metrics=metrics
            )

    def test_wrapper_uses_default_metrics(self):
        """Test that wrapper uses default metrics when none provided."""
        vector_docs = [{"id": "doc1", "content": "Content 1"}]
        bm25_docs = [{"id": "doc2", "content": "Content 2"}]
        
        # Should not raise errors (uses default metrics)
        result = rrf_fusion_with_metrics(vector_docs, bm25_docs)
        assert len(result) == 2


class TestIntegrationScenarios:
    """Integration test scenarios that mirror real-world usage."""

    def test_typical_workload(self):
        """Test fusion with typical workload sizes and characteristics."""
        # Simulate typical vector + BM25 retrieval results
        vector_docs = [
            {
                "id": f"vec_doc_{i}",
                "content": f"Document {i} about error codes and debugging techniques",
                "metadata": {"source": "documentation", "relevance": "high"}
            }
            for i in range(1, 21)  # 20 vector docs
        ]
        
        bm25_docs = [
            {
                "id": f"bm25_doc_{i}",
                "content": f"Technical document {i} containing exact error codes and solutions",
                "metadata": {"source": "kb", "relevance": "medium"}
            }
            for i in range(1, 21)  # 20 BM25 docs
        ]
        
        # Add some overlap (documents found by both retrievers)
        overlap_docs = [
            {"id": "overlap_doc_1", "content": "Common document found by both methods"},
            {"id": "overlap_doc_2", "content": "Another common document"},
        ]
        
        # Insert overlap into both lists
        vector_docs[5:7] = overlap_docs
        bm25_docs[10:12] = overlap_docs
        
        # Perform fusion
        result = rrf_fusion(
            vector_docs=vector_docs,
            bm25_docs=bm25_docs,
            top_k=50,
            vector_weight=0.5,
            bm25_weight=0.5
        )
        
        # Verify results
        assert len(result) <= 50  # Top-k limit
        
        # Overlap documents should rank higher
        overlap_ids = {"overlap_doc_1", "overlap_doc_2"}
        overlap_ranked_high = all(
            doc["id"] in overlap_ids for doc in result[:4]  # First few positions
        )
        
        # At least some overlap docs should be in top ranks
        assert overlap_ranked_high or any(
            doc["id"] in overlap_ids for doc in result[:10]
        )
        
        # All results should have rrf_score
        for doc in result:
            assert "rrf_score" in doc
            assert isinstance(doc["rrf_score"], float)

    def test_edge_case_maximum_top_k(self):
        """Test with maximum reasonable top_k value."""
        # Create many documents
        vector_docs = [{"id": f"vec_{i}", "content": f"Content {i}"} for i in range(100)]
        bm25_docs = [{"id": f"bm25_{i}", "content": f"Content {i}"} for i in range(100)]
        
        # Request large top_k
        result = rrf_fusion(vector_docs, bm25_docs, top_k=150)
        
        # Should not exceed available unique documents
        unique_ids = {doc["id"] for doc in result}
        assert len(result) == min(150, len(unique_ids))

    def test_weight_configuration_edge_cases(self):
        """Test edge cases for weight configurations."""
        doc = {"id": "test_doc", "content": "Test content"}
        
        # When same document appears in both lists at same rank,
        # weights don't affect final score because it's same rank position
        result_vector_heavy = rrf_fusion(
            [doc], [doc], vector_weight=0.8, bm25_weight=0.2
        )
        
        result_bm25_heavy = rrf_fusion(
            [doc], [doc], vector_weight=0.2, bm25_weight=0.8
        )
        
        # Scores should be identical because same document at same rank
        # from both retrievers: score = (0.8 + 0.2)/(60+1) = 1.0/(60+1)
        assert result_vector_heavy[0]["rrf_score"] == result_bm25_heavy[0]["rrf_score"]
        
        # Test with different rank positions to see weight effects
        vector_docs = [
            {"id": "doc1", "content": "Content 1"},  # Rank 1
            {"id": "doc2", "content": "Content 2"},  # Rank 2
        ]
        bm25_docs = [
            {"id": "doc3", "content": "Content 3"},  # Rank 1
            {"id": "doc1", "content": "Content 1"},  # Rank 2 - overlap at different rank
        ]
        
        # With balanced weights, doc1 should get both contributions
        result_balanced = rrf_fusion(vector_docs, bm25_docs, vector_weight=0.5, bm25_weight=0.5)
        
        # Doc1 should be found at rank 1 (vector) and rank 2 (bm25)
        # Score = 0.5/(60+1) + 0.5/(60+2)
        doc1_score = None
        for doc in result_balanced:
            if doc["id"] == "doc1":
                doc1_score = doc["rrf_score"]
                break
        
        assert doc1_score is not None
        expected_score = 0.5/(60+1) + 0.5/(60+2)
        assert abs(doc1_score - expected_score) < 0.001