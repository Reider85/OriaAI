"""RAG (Retrieval-Augmented Generation) configuration classes."""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class RetrievalStrategy(str, Enum):
    """Retrieval strategy for RAG pipeline."""
    
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"


@dataclass
class RetrieverConfig:
    """Configuration for RAG retrieval pipeline.
    
    Contains settings for both retrieval and reranking components.
    """
    
    # Reranker configuration (C-4 Pipeline integration)
    reranker_name: str = "bge"          # name from RerankerRegistry
    reranker_top_k: int = 5             # final chunks for LLM context
    reranker_enabled: bool = True        # toggle (False = skip rerank)
    
    # Retrieval strategy (D-1 placeholder, not yet implemented)
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    
    # Vector retrieval settings
    vector_top_k: int = 20               # number of documents to retrieve
    vector_fetch_k: int = 40            # number of documents to fetch for MMR
    vector_search_type: str = "mmr"      # mmr|similarity
    vector_lambda_mult: float = 0.5      # diversity parameter for MMR
    vector_score_threshold: float = 0.0  # minimum score threshold
    
    # BM25 retrieval settings (D-1 placeholder)
    bm25_top_k: int = 20                 # number of documents to retrieve
    bm25_weight: float = 0.5            # weight for BM25 in hybrid mode
    
    # Hybrid retrieval settings (D-1 placeholder)
    vector_weight: float = 0.5           # weight for vector similarity
    hybrid_top_k: int = 50               # number of documents after fusion
    
    # Factory method to create from environment
    @classmethod
    def from_env(cls) -> "RetrieverConfig":
        """Create config from environment variables with sensible defaults."""
        return cls(
            reranker_name=os.getenv("RERANKER_NAME", "bge"),
            reranker_top_k=int(os.getenv("RERANKER_TOP_K", "5")),
            reranker_enabled=os.getenv("RERANKER_ENABLED", "true").lower() == "true",
            retrieval_strategy=RetrievalStrategy(os.getenv("RETRIEVAL_STRATEGY", "hybrid")),
            vector_top_k=int(os.getenv("VECTOR_TOP_K", "20")),
            vector_fetch_k=int(os.getenv("VECTOR_FETCH_K", "40")),
            vector_search_type=os.getenv("VECTOR_SEARCH_TYPE", "mmr"),
            vector_lambda_mult=float(os.getenv("VECTOR_LAMBDA_MULT", "0.5")),
            vector_score_threshold=float(os.getenv("VECTOR_SCORE_THRESHOLD", "0.0")),
            bm25_top_k=int(os.getenv("BM25_TOP_K", "20")),
            bm25_weight=float(os.getenv("BM25_WEIGHT", "0.5")),
            vector_weight=float(os.getenv("VECTOR_WEIGHT", "0.5")),
            hybrid_top_k=int(os.getenv("HYBRID_TOP_K", "50")),
        )
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.reranker_top_k <= 0:
            raise ValueError("reranker_top_k must be positive")
        if self.vector_top_k <= 0:
            raise ValueError("vector_top_k must be positive")
        if self.bm25_top_k <= 0:
            raise ValueError("bm25_top_k must be positive")
        if self.hybrid_top_k <= 0:
            raise ValueError("hybrid_top_k must be positive")
        if self.vector_weight <= 0 or self.vector_weight >= 1:
            raise ValueError("vector_weight must be between 0 and 1")
        if self.bm25_weight <= 0 or self.bm25_weight >= 1:
            raise ValueError("bm25_weight must be between 0 and 1")
        if self.vector_weight + self.bm25_weight != 1.0:
            raise ValueError("vector_weight + bm25_weight must equal 1.0")