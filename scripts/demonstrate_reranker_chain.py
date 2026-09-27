#!/usr/bin/env python3
"""
Demonstration of RerankerChain fallback functionality.

This script shows how the RerankerChain gracefully falls back through
different rerankers when the primary ones fail.
"""

import asyncio
import logging
from llm_client.rag.config import RetrieverConfig
from llm_client.rag.rerankers.chain import RerankerChain
from llm_client.rag.rerankers.identity import IdentityReranker
from llm_client.rag.rerankers.registry import RerankerRegistry

# Set up logging to see fallback events
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FailingReranker:
    """A reranker that fails for demonstration purposes."""
    
    def __init__(self, name, fail_health_check=False, fail_rerank=False):
        self.name = name
        self.fail_health_check = fail_health_check
        self.fail_rerank = fail_rerank
        self.rerank_calls = []
    
    @property
    def name(self) -> str:
        return self._name
    
    @name.setter
    def name(self, value: str):
        self._name = value
    
    async def health_check(self) -> bool:
        if self.fail_health_check:
            logger.info(f"FAIL {self.name}: Health check failed")
            return False
        logger.info(f"OK {self.name}: Health check passed")
        return True
    
    async def rerank(self, query: str, documents, top_k: int = 5, batch_size: int = 8):
        self.rerank_calls.append((query, documents, top_k, batch_size))
        
        if self.fail_rerank:
            logger.info(f"FAIL {self.name}: Rerank failed")
            raise RuntimeError(f"{self.name} rerank failed")
        
        logger.info(f"OK {self.name}: Rerank succeeded")
        # Return some dummy results
        return [
            type('RerankResult', (), {
                'doc_id': str(i),
                'score': 0.9 - i * 0.1,
                'original_index': i
            })() for i in range(min(top_k, len(documents)))
        ]


async def demonstrate_fallback_chain():
    """Demonstrate the fallback chain functionality."""
    
    print("Demonstrating RerankerChain fallback functionality\n")
    
    # Create test documents
    documents = [
        {"content": "Document 1 about AI and machine learning", "id": "doc1"},
        {"content": "Document 2 about artificial intelligence", "id": "doc2"},
        {"content": "Document 3 about deep learning", "id": "doc3"},
        {"content": "Document 4 about neural networks", "id": "doc4"},
        {"content": "Document 5 about computer vision", "id": "doc5"},
    ]
    
    query = "What is machine learning?"
    
    # Scenario 1: Primary fails, fallback succeeds
    print("Scenario 1: Primary fails, fallback succeeds")
    print("-" * 50)
    
    primary = FailingReranker("Primary", fail_rerank=True)
    fallback = FailingReranker("Fallback")
    chain = RerankerChain([primary, fallback])
    
    try:
        results = await chain.rerank(query, documents, top_k=3)
        print(f"SUCCESS Got {len(results)} results")
        print(f"Scores: {[r.score for r in results]}")
    except Exception as e:
        print(f"ERROR Unexpected error: {e}")
    
    print(f"\nCall counts: Primary={len(primary.rerank_calls)}, Fallback={len(fallback.rerank_calls)}")
    print()
    
    # Scenario 2: All fail, fallback to identity
    print("Scenario 2: All rerankers fail, fallback to identity")
    print("-" * 50)
    
    primary2 = FailingReranker("Primary2", fail_rerank=True)
    fallback2 = FailingReranker("Fallback2", fail_rerank=True)
    chain2 = RerankerChain([primary2, fallback2])
    
    try:
        results = await chain2.rerank(query, documents, top_k=3)
        print(f"SUCCESS Got {len(results)} results")
        print(f"Scores: {[r.score for r in results]} (should be 1.0 for identity fallback)")
    except Exception as e:
        print(f"ERROR Unexpected error: {e}")
    
    print(f"\nCall counts: Primary2={len(primary2.rerank_calls)}, Fallback2={len(fallback2.rerank_calls)}")
    print()
    
    # Scenario 3: Health check failure
    print("Scenario 3: Health check failure")
    print("-" * 50)
    
    primary3 = FailingReranker("Primary3", fail_health_check=True)
    fallback3 = FailingReranker("Fallback3")
    chain3 = RerankerChain([primary3, fallback3])
    
    try:
        results = await chain3.rerank(query, documents, top_k=3)
        print(f"SUCCESS Got {len(results)} results")
        print(f"Scores: {[r.score for r in results]}")
    except Exception as e:
        print(f"ERROR Unexpected error: {e}")
    
    print(f"\nCall counts: Primary3={len(primary3.rerank_calls)}, Fallback3={len(fallback3.rerank_calls)}")
    print()
    
    # Scenario 4: Integration with RetrieverConfig
    print("Scenario 4: Integration with RetrieverConfig")
    print("-" * 50)
    
    # Show how the config would work
    config = RetrieverConfig(
        reranker_name="primary",  # This gets ignored when fallback_chain is set
        reranker_top_k=3,
        reranker_enabled=True,
        reranker_fallback_chain=["cohere", "bge", "identity"],  # Example chain
    )
    
    print("Configuration with fallback chain:")
    print(f"  reranker_name: {config.reranker_name}")
    print(f"  reranker_fallback_chain: {config.reranker_fallback_chain}")
    print(f"  reranker_enabled: {config.reranker_enabled}")
    print()
    
    # Show how real IdentityReranker works
    print("Testing real IdentityReranker:")
    identity = IdentityReranker()
    results = await identity.rerank(query, documents, top_k=3)
    print(f"SUCCESS Identity reranker returned {len(results)} results")
    print(f"Scores: {[r.score for r in results]} (should be 1.0)")
    print(f"Original indices: {[r.original_index for r in results]}")
    print()


async def main():
    """Main demonstration function."""
    await demonstrate_fallback_chain()
    print("Demonstration complete!")
    print("\nKey takeaways:")
    print("  • RerankerChain tries rerankers in order")
    print("  • Falls back to next reranker on failure")
    print("  • Uses internal identity fallback if all fail")
    print("  • Health checks are performed before each rerank")
    print("  • Configurable via RetrieverConfig.reranker_fallback_chain")


if __name__ == "__main__":
    asyncio.run(main())