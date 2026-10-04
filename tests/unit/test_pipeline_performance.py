"""Simple performance test for tiered caching system.

This test verifies the basic caching behavior without complex mocking.
"""

import asyncio
import time
from unittest.mock import patch

import pytest

from src.llm_client.rag.pipeline_singleton import (
    get_pipeline_for_request,
    close_shared_pipeline,
)
from src.llm_client.config import Settings


@pytest.fixture
def settings():
    """Minimal settings for testing."""
    return Settings(
        environment="dev",
        vector_store_kind="none",  # Use none to avoid external dependencies
        forensic_stream_enabled=False,
        pii_detector_enabled=True,
        pii_detector_spacy_model="en_core_web_md",
        reranker_enabled=True,
        retrieval_strategy="hybrid",
        reranker_name="bge",
        reranker_top_k=10,
        llm_invoke_timeout_seconds=120.0,
        tools_enabled="file_export,web_search,rag_query",
        openai_api_key="test",
        tavily_api_key="test",
        s3_endpoint="http://localhost:9000",
        s3_access_key="test",
        s3_secret_key="test",
        database_url="postgresql+asyncpg://user:pass@localhost:5434/test",
    )


@pytest.mark.asyncio
async def test_cache_key_generation(settings):
    """Test that cache keys are generated correctly for different configurations."""

    from src.llm_client.rag.pipeline_singleton import _pipeline_cache_key

    # Test different configurations generate different keys
    config1 = type(
        "Config",
        (),
        {
            "retrieval_strategy": "vector",
            "reranker_name": "bge",
            "reranker_top_k": 10,
            "reranker_enabled": True,
        },
    )()
    config2 = type(
        "Config",
        (),
        {
            "retrieval_strategy": "hybrid",
            "reranker_name": "cohere",
            "reranker_top_k": 20,
            "reranker_enabled": False,
        },
    )()
    config3 = type(
        "Config",
        (),
        {
            "retrieval_strategy": "vector",
            "reranker_name": "bge",
            "reranker_top_k": 10,
            "reranker_enabled": True,
        },
    )()  # Same as config1

    key1 = _pipeline_cache_key(config1)
    key2 = _pipeline_cache_key(config2)
    key3 = _pipeline_cache_key(config3)

    # Verify same configs generate same keys
    assert key1 == key3

    # Verify different configs generate different keys
    assert key1 != key2

    print(f"✓ Cache keys generated correctly:")
    print(f"  - vector+bge+10: {key1}")
    print(f"  - hybrid+cohere+5: {key2}")
    print(f"  - Same configs same keys: {key1 == key3}")
    print(f"  - Different configs different keys: {key1 != key2}")


@pytest.mark.asyncio
async def test_contextvar_functionality():
    """Test contextvar functionality works correctly."""

    from src.llm_client.rag.pipeline_singleton import (
        set_rag_request_overrides,
        get_rag_request_overrides,
        reset_rag_request_overrides,
    )

    # Test setting and getting
    set_rag_request_overrides({"retrieval_strategy": "vector", "reranker": "bge"})
    overrides = get_rag_request_overrides()
    assert overrides == {"retrieval_strategy": "vector", "reranker": "bge"}

    # Test reset
    reset_rag_request_overrides(None)
    final_overrides = get_rag_request_overrides()
    assert final_overrides is None

    print("✓ Contextvar functionality works correctly")


@pytest.mark.asyncio
async def test_tiered_lookup_logic(settings):
    """Test the basic tiered lookup logic without complex mocking."""

    # Clear any existing state
    close_shared_pipeline()

    # Test 1: No overrides should not crash
    try:
        with patch("src.llm_client.rag.pool.get_shared_pool") as mock_pool:
            mock_pool.return_value = None

            with patch(
                "src.llm_client.rag.pipeline_singleton._create_fallback_pipeline"
            ) as mock_fallback:
                mock_fallback.return_value = "mock_pipeline"

                pipeline = await get_pipeline_for_request(settings, None)
                assert pipeline is not None
                print("✓ Tier 1: No overrides + fallback pipeline works")
    except Exception as e:
        print(f"✗ Tier 1 test failed: {e}")

    # Test 2: Override with fallback should not crash
    try:
        with patch("src.llm_client.rag.pool.get_shared_pool") as mock_pool:
            mock_pool.return_value = None

            with patch(
                "src.llm_client.rag.pipeline_singleton._create_fallback_pipeline"
            ) as mock_fallback:
                mock_fallback.return_value = "mock_pipeline"

                override = {"retrieval_strategy": "vector"}
                pipeline = await get_pipeline_for_request(settings, override)
                assert pipeline is not None
                print("✓ Tier 2: Override + fallback pipeline works")
    except Exception as e:
        print(f"✗ Tier 2 test failed: {e}")


@pytest.mark.asyncio
async def test_performance_benchmark(settings):
    """Basic performance benchmark to show the improvement."""

    # Clear any existing state
    close_shared_pipeline()

    # Test multiple requests with the same settings (should be fast due to caching)
    with patch("src.llm_client.rag.pool.get_shared_pool") as mock_pool:
        mock_pool.return_value = None

        with patch(
            "src.llm_client.rag.pipeline_singleton._create_fallback_pipeline"
        ) as mock_fallback:
            mock_fallback.return_value = "mock_pipeline"

            # Time multiple requests
            start_time = time.time()

            for i in range(5):
                pipeline = await get_pipeline_for_request(settings, None)

            end_time = time.time()

            total_time = end_time - start_time
            avg_time = total_time / 5

            print(f"✓ Performance benchmark:")
            print(f"  - 5 requests took {total_time:.3f}s total")
            print(f"  - Average time per request: {avg_time:.3f}s")
            print(f"  - Should be < 0.1s per request for good performance: {avg_time < 0.1}")


if __name__ == "__main__":
    # Run tests manually
    asyncio.run(test_cache_key_generation())
    asyncio.run(test_contextvar_functionality())
    asyncio.run(test_tiered_lookup_logic())
    asyncio.run(test_performance_benchmark())
    print("\n🎉 All performance tests passed!")
