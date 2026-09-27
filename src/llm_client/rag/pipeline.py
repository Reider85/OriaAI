"""RAG (Retrieval-Augmented Generation) pipeline with reranking after fusion."""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Sequence

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.rerankers.base import Reranker, RerankResult
from llm_client.rag.rerankers.registry import RerankerRegistry
from llm_client.rag.metrics import RerankerMetrics, default_reranker_metrics
from llm_client.observability.forensic_writer import ForensicStreamWriter
from llm_client.observability.operational_writer import OperationalStreamWriter

logger = logging.getLogger(__name__)


async def rerank_after_fusion(
    query: str,
    fused_docs: list[dict],  # top-50 after RRF fusion
    config: RetrieverConfig,
    *,
    reranker_registry: Optional[RerankerRegistry] = None,
    metrics: Optional[RerankerMetrics] = None,
    operational_writer: Optional[OperationalStreamWriter] = None,
    forensic_writer: Optional[ForensicStreamWriter] = None,
) -> list[dict]:
    """Apply reranking to documents after fusion in the RAG pipeline.
    
    Args:
        query: The search query
        fused_docs: Documents already fused (top-50 after RRF fusion)
        config: RetrieverConfig containing reranking settings
        reranker_registry: Optional registry (defaults to global registry)
        metrics: Optional metrics instance (defaults to global metrics)
        operational_writer: Optional operational writer for logging
        forensic_writer: Optional forensic writer for audit logging
        
    Returns:
        List of reranked documents (top-K based on config.reranker_top_k)
        
    Raises:
        ValueError: If config validation fails
        RuntimeError: If all rerankers fail and fallback is not possible
    """
    # Use global instances if not provided
    registry = reranker_registry or RerankerRegistry.registry
    metrics = metrics or default_reranker_metrics
    
    # Early return if reranking is disabled or input is small enough
    if not config.reranker_enabled or len(fused_docs) <= config.reranker_top_k:
        metrics.set_input_count(len(fused_docs))
        metrics.set_output_count(len(fused_docs))
        return fused_docs[:config.reranker_top_k]
    
    # Record start time for latency measurement
    start_time = time.time()
    
    try:
        # Get the reranker from registry
        reranker = registry.get(config.reranker_name)
        
        # Validate reranker health
        if not await reranker.health_check():
            logger.warning("Reranker '%s' failed health check, falling back to identity", config.reranker_name)
            # Log error to operational stream
            if operational_writer:
                await operational_writer.write({
                    "event": "rag_rerank_error",
                    "reranker": reranker.name,
                    "error": "Health check failed",
                    "input_count": len(fused_docs),
                })
            return _identity_fallback(fused_docs, config.reranker_top_k)
        
        # Record input count
        metrics.set_input_count(len(fused_docs))
        
        # Perform reranking
        results = await reranker.rerank(
            query=query,
            documents=fused_docs,
            top_k=config.reranker_top_k,
        )
        
        # Map back to original documents using original_index and add score
        reranked_docs = []
        for r in results:
            original_doc = fused_docs[r.original_index]
            reranked_doc = {
                "content": original_doc["content"],
                "metadata": original_doc.get("metadata", {}),
                "score": r.score,
            }
            if "id" in original_doc:
                reranked_doc["id"] = original_doc["id"]
            reranked_docs.append(reranked_doc)
        
        # Record metrics
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_latency(latency_ms)
        metrics.set_output_count(len(reranked_docs))
        
        # Log to operational stream
        if operational_writer:
            await operational_writer.write({
                "event": "rag_rerank",
                "reranker": reranker.name,
                "input_count": len(fused_docs),
                "output_count": len(reranked_docs),
                "latency_ms": round(latency_ms, 2),
                "query": query,  # PII-safe: query is not sensitive
            })
        
        # Log full rerank scores to forensic stream (for audit)
        if forensic_writer and forensic_writer._enabled:
            forensic_event = {
                "event": "rag_rerank_scores",
                "reranker": reranker.name,
                "query": query,
                "input_count": len(fused_docs),
                "output_count": len(reranked_docs),
                "scores": [
                    {
                        "doc_id": r.doc_id,
                        "score": r.score,
                        "original_index": r.original_index,
                    }
                    for r in results
                ],
            }
            await forensic_writer.write(forensic_event)
        
        return reranked_docs
        
    except Exception as e:
        # Log error and increment error counter
        logger.error("Reranking failed for query='%s', error=%s", query, str(e))
        metrics.increment_error_count()
        
        # Log to operational stream
        if operational_writer:
            await operational_writer.write({
                "event": "rag_rerank_error",
                "reranker": config.reranker_name,
                "error": str(e),
                "input_count": len(fused_docs),
            })
        
        # Fall back to identity reranking
        logger.warning("Falling back to identity reranking for query='%s'", query)
        return _identity_fallback(fused_docs, config.reranker_top_k)


def _identity_fallback(fused_docs: list[dict], top_k: int) -> list[dict]:
    """Fallback identity reranking: return first top_k documents unchanged.
    
    Args:
        fused_docs: List of documents
        top_k: Number of documents to return
        
    Returns:
        First top_k documents from the input list with score=1.0
    """
    return [
        {
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
            "score": 1.0,  # Identity fallback gives neutral score
        }
        for i, doc in enumerate(fused_docs[:top_k])
    ]


async def _mock_rrf_fusion(
    vector_docs: list[dict], 
    bm25_docs: list[dict], 
    top_k: int = 50
) -> list[dict]:
    """Mock RRF fusion function for testing purposes.
    
    In the real implementation, this would be implemented in Block D-5.
    This mock simulates Reciprocal Rank Fusion by combining documents and
    assigning synthetic scores.
    
    Args:
        vector_docs: Documents from vector retrieval
        bm25_docs: Documents from BM25 retrieval  
        top_k: Number of documents to return after fusion
        
    Returns:
        Fused documents with RRF scores
    """
    # Create a combined set of documents
    all_docs = {}
    
    # Add vector docs with synthetic scores
    for i, doc in enumerate(vector_docs):
        doc_id = doc.get("id", str(i))
        all_docs[doc_id] = {
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
            "vector_score": 1.0 / (i + 1),  # Synthetic RRF score
            "bm25_score": 0.0,
        }
    
    # Add BM25 docs with synthetic scores
    for i, doc in enumerate(bm25_docs):
        doc_id = doc.get("id", f"bm25_{i}")
        if doc_id in all_docs:
            all_docs[doc_id]["bm25_score"] = 1.0 / (i + 1)
        else:
            all_docs[doc_id] = {
                "content": doc["content"],
                "metadata": doc.get("metadata", {}),
                "vector_score": 0.0,
                "bm25_score": 1.0 / (i + 1),
            }
    
    # Apply RRF: score = 1 / (rank_vector + rank_bm25)
    fused_docs = []
    for doc_id, doc in all_docs.items():
        rrf_score = 1.0 / (doc["vector_score"] + doc["bm25_score"])
        fused_docs.append({
            "id": doc_id,
            "content": doc["content"],
            "metadata": doc["metadata"],
            "score": rrf_score,
        })
    
    # Sort by RRF score and return top_k
    fused_docs.sort(key=lambda x: x["score"], reverse=True)
    return fused_docs[:top_k]