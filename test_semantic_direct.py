#!/usr/bin/env python3
"""Minimal test for semantic_cache without package imports."""

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
    # Import the module directly by file path to avoid __init__.py
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "semantic_cache", 
        os.path.join(os.path.dirname(__file__), "src", "llm_client", "rag", "semantic_cache.py")
    )
    semantic_cache_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(semantic_cache_module)
    
    SemanticAnswerCache = semantic_cache_module.SemanticAnswerCache
    get_semantic_cache = semantic_cache_module.get_semantic_cache
    CacheHitResult = semantic_cache_module.CacheHitResult
    
    print("SUCCESS: Successfully imported semantic_cache module directly")
    
    # Test basic instantiation
    cache = SemanticAnswerCache(
        redis_url="redis://localhost:6379/2",
        embeddings=None,  # Will be mocked in actual test
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
    
except ImportError as e:
    print(f"ERROR: Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Error: {e}")
    sys.exit(1)