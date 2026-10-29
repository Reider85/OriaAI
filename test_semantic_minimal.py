#!/usr/bin/env python3
"""Minimal test for semantic_cache without pytest dependencies."""

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
    # Import directly from the file to avoid __init__.py dependencies
    from llm_client.rag.semantic_cache import SemanticAnswerCache, get_semantic_cache
    print("✅ Successfully imported SemanticAnswerCache")
    
    # Test basic instantiation
    cache = SemanticAnswerCache(
        redis_url="redis://localhost:6379/2",
        embeddings=None,  # Will be mocked in actual test
        ttl_seconds=86400,
        similarity_threshold=0.92,
        max_entries=10000,
    )
    print("✅ Successfully created SemanticAnswerCache instance")
    
    # Test singleton factory
    cache2 = get_semantic_cache()
    if cache2 is not None:
        print("✅ get_semantic_cache() returned instance")
    else:
        print("⚠️  get_semantic_cache() returned None (cache disabled)")
    
    print("🎉 All basic tests passed!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)