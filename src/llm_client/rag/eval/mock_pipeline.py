"""Mock retrieval pipeline for A/B testing RAG quality."""

import math
import re
import time
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.pipeline import rerank_after_fusion


class MockRetrievalPipeline:
    """Mock RAG pipeline that simulates vector + BM25 retrieval + reranking.
    
    For A/B testing purposes when real retrieval isn't implemented yet.
    Uses TF-IDF for vector similarity and BM25 term frequency for lexical search.
    """
    
    def __init__(self, corpus: list[dict[str, Any]]):
        """Initialize with document corpus.
        
        Args:
            corpus: List of documents with 'id', 'content', 'metadata' fields
        """
        self.corpus = corpus
        self.corpus_texts = [doc["content"] for doc in corpus]
        self.corpus_ids = [doc["id"] for doc in corpus]
        
        # Initialize TF-IDF vectorizer for vector search
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.8
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus_texts)
        
        # Pre-compute document lengths for BM25
        self.doc_lengths = [len(doc["content"].split()) for doc in corpus]
        self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths)
        
        # BM25 parameters
        self.k1 = 1.2  # document saturation parameter
        self.b = 0.75  # length normalization parameter
    
    async def search(self, query: str, config: RetrieverConfig) -> list[dict[str, Any]]:
        """Perform search based on retrieval strategy.
        
        Args:
            query: Search query
            config: RetrieverConfig with retrieval strategy and parameters
            
        Returns:
            List of retrieved documents with scores
        """
        start_time = time.time()
        
        if config.retrieval_strategy.value == "vector":
            vector_docs = await self._vector_search(query, config.vector_top_k)
            bm25_docs = []
        elif config.retrieval_strategy.value == "bm25":
            vector_docs = []
            bm25_docs = await self._bm25_search(query, config.bm25_top_k)
        else:  # hybrid
            vector_docs = await self._vector_search(query, config.vector_top_k)
            bm25_docs = await self._bm25_search(query, config.bm25_top_k)
            vector_docs = await self._rrf_fusion(vector_docs, bm25_docs, config.hybrid_top_k)
        
        # Apply reranking if enabled
        if config.reranker_enabled:
            reranked_docs = await rerank_after_fusion(
                query=query,
                fused_docs=vector_docs,
                config=config,
            )
        else:
            reranked_docs = vector_docs[:config.reranker_top_k]
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Add latency to each document for reporting
        for doc in reranked_docs:
            doc["latency_ms"] = latency_ms
        
        return reranked_docs[:config.reranker_top_k]
    
    async def _vector_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Simulate vector search using TF-IDF cosine similarity."""
        query_vector = self.vectorizer.transform([query])
        
        # Calculate cosine similarity
        similarities = cosine_similarity(query_vector, self.tfidf_matrix)[0]
        
        # Get top-k documents
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            doc = self.corpus[idx].copy()
            doc["score"] = float(similarities[idx])
            doc["retrieval_method"] = "vector"
            results.append(doc)
        
        return results
    
    async def _bm25_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Simulate BM25 search using term frequency scoring."""
        query_terms = re.findall(r'\b\w+\b', query.lower())
        
        scores = []
        for i, doc in enumerate(self.corpus):
            doc_text = doc["content"].lower()
            doc_terms = re.findall(r'\b\w+\b', doc_text)
            
            # Calculate BM25 score
            score = 0.0
            for term in query_terms:
                term_freq = doc_terms.count(term)
                if term_freq > 0:
                    # BM25 formula
                    idf = math.log((len(self.corpus) + 1) / 
                                 (sum(1 for d in self.corpus if term in d["content"].lower()) + 1) + 1)
                    numerator = term_freq * (self.k1 + 1)
                    denominator = term_freq + self.k1 * (1 - self.b + self.b * 
                                                       (self.doc_lengths[i] / self.avg_doc_length))
                    score += idf * (numerator / denominator)
            
            if score > 0:
                scores.append((i, score))
        
        # Sort by score and get top-k
        scores.sort(key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, _ in scores[:top_k]]
        
        results = []
        for idx in top_indices:
            doc = self.corpus[idx].copy()
            doc["score"] = scores[idx][1]
            doc["retrieval_method"] = "bm25"
            results.append(doc)
        
        return results
    
    async def _rrf_fusion(self, vector_docs: list[dict[str, Any]], 
                          bm25_docs: list[dict[str, Any]], 
                          top_k: int) -> list[dict[str, Any]]:
        """Reciprocal Rank Fusion of vector and BM25 results."""
        # Create a mapping of document IDs to scores from both methods
        doc_scores = {}
        
        # Add vector scores
        for rank, doc in enumerate(vector_docs):
            doc_id = doc["id"]
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {"vector_score": 0.0, "bm25_score": 0.0, "doc": doc}
            doc_scores[doc_id]["vector_score"] += 1.0 / (rank + 1)
        
        # Add BM25 scores
        for rank, doc in enumerate(bm25_docs):
            doc_id = doc["id"]
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {"vector_score": 0.0, "bm25_score": 0.0, "doc": doc}
            doc_scores[doc_id]["bm25_score"] += 1.0 / (rank + 1)
        
        # Apply RRF: score = 1 / (rank_vector + rank_bm25)
        fused_docs = []
        for doc_id, scores in doc_scores.items():
            rrf_score = scores["vector_score"] + scores["bm25_score"]
            fused_doc = scores["doc"].copy()
            fused_doc["score"] = rrf_score
            fused_doc["retrieval_method"] = "hybrid"
            fused_docs.append(fused_doc)
        
        # Sort by RRF score and return top-k
        fused_docs.sort(key=lambda x: x["score"], reverse=True)
        return fused_docs[:top_k]