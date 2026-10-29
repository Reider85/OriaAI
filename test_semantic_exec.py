#!/usr/bin/env python3
"""Test for semantic_cache with absolute imports."""

import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set minimal env vars to avoid config validation issues
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test-placeholder")
os.environ.setdefault("REDIS_SEMANTIC_CACHE_URL", "redis://localhost:6379/2")
os.environ.setdefault("SEMANTIC_CACHE_ENABLED", "true")

try:
    # Import the modules we need first
    from llm_client.config import Settings
    from llm_client.observability.llm_metrics import record_cache_hit
    
    # Create a minimal settings object for testing
    settings = Settings()
    
    # Mock the dependencies
    class MockOpenAIEmbeddings:
        async def aembed_query(self, query):
            return [0.1] * 1536  # Mock 1536-dimensional vector
    
    # Now import the semantic cache module by executing it directly
    exec(open('src/llm_client/rag/semantic_cache.py').read())
    
    print("SUCCESS: Successfully loaded semantic_cache code")
    
    # Test basic instantiation
    cache = SemanticAnswerCache(
        redis_url="redis://localhost:6379/2",
        embeddings=MockOpenAIEmbeddings(),
        ttl_seconds=86400,
        similarity_threshold=0.92,
        max_entries=10000,
    )
    print("SUCCESS: Successfully created SemanticAnswerCache instance")
    
    # Test singleton factory
    cache2 = get_semantic_cache()
    if cache2 is not None:
        print("SUCCESS: get_semantic_cache() returned instance")
    else:
        print("WARNING: get_semantic_cache() returned None (cache disabled)")
    
    print("SUCCESS: All basic tests passed!")
    
except Exception as e:
    print(f"ERROR: Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)