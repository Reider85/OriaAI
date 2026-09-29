"""Unit tests for web_search tool via Tavily API (AG-5, Phase 2)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from llm_client.agent.tools.web_search import web_search, WebSearchArgs, _web_search_impl
from llm_client.config import settings


@pytest.fixture
def mock_tavily_response():
    """Mock Tavily API response."""
    return {
        "results": [
            {
                "title": "Python async programming",
                "url": "https://example.com/python-async",
                "content": "Async programming in Python allows for concurrent execution using async/await syntax.",
                "score": 0.95,
            },
            {
                "title": "LangChain tutorial",
                "url": "https://langchain.com/docs",
                "content": "LangChain is a framework for developing applications powered by language models.",
                "score": 0.88,
            },
            {
                "title": "HTTPX async client",
                "url": "https://www.python-httpx.org/",
                "content": "HTTPX is an HTTP client for Python 3, fully compatible with the requests API.",
                "score": 0.82,
            }
        ]
    }


@pytest.mark.asyncio
async def test_web_search_basic_functionality(mock_tavily_response):
    """Test basic web search functionality with mocked Tavily API."""
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch.object(settings, "tavily_api_key", "test-api-key"), \
         patch.object(settings, "tavily_timeout_seconds", 30.0), \
         patch.object(settings, "tavily_search_depth", "basic"), \
         patch.object(settings, "tavily_snippet_max_chars", 500):
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        
        results = await _web_search_impl("Python async", max_results=3)
        
        # Verify API call was made correctly
        mock_client.post.assert_called_once_with(
            "https://api.tavily.com/search",
            headers={"Authorization": "Bearer test-api-key"},
            json={
                "query": "Python async",
                "max_results": 3,
                "include_answer": False,
                "search_depth": "basic",
            },
        )
        
        # Verify results structure
        assert len(results) == 3
        assert all("title" in r for r in results)
        assert all("url" in r for r in results)
        assert all("snippet" in r for r in results)
        assert all("score" in r for r in results)
        
        # Verify content truncation (should be <= 500 chars)
        for result in results:
            assert len(result["snippet"]) <= 500
        
        # Verify first result matches expected data
        assert results[0]["title"] == "Python async programming"
        assert results[0]["url"] == "https://example.com/python-async"
        assert "Async programming in Python" in results[0]["snippet"]
        assert results[0]["score"] == 0.95


@pytest.mark.asyncio
async def test_web_search_max_results_validation():
    """Test max_results parameter validation."""
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch.object(settings, "tavily_api_key", "test-api-key"), \
         patch.object(settings, "tavily_timeout_seconds", 30.0):
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = AsyncMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        
        # Test with valid max_results
        await _web_search_impl("test query", max_results=5)
        
        # Test with default max_results
        await _web_search_impl("test query")


@pytest.mark.asyncio
async def test_web_search_missing_api_key():
    """Test that RuntimeError is raised when TAVILY_API_KEY is not set."""
    with patch.object(settings, "tavily_api_key", ""):
        with pytest.raises(RuntimeError, match="web_search tool requires TAVILY_API_KEY"):
            await _web_search_impl("test query")


@pytest.mark.asyncio
async def test_web_search_api_error():
    """Test that API errors are propagated."""
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch.object(settings, "tavily_api_key", "test-api-key"), \
         patch.object(settings, "tavily_timeout_seconds", 30.0):
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Make the API call raise an exception
        mock_client.post.side_effect = Exception("API Error")
        
        with pytest.raises(Exception, match="API Error"):
            await _web_search_impl("test query")


@pytest.mark.asyncio
async def test_web_search_snippet_truncation():
    """Test that long content snippets are truncated to max_chars."""
    long_content = "This is a very long content that exceeds the maximum allowed length. " * 100
    mock_tavily_response = {
        "results": [{"title": "Test", "url": "https://test.com", "content": long_content, "score": 0.9}]
    }
    
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch.object(settings, "tavily_api_key", "test-api-key"), \
         patch.object(settings, "tavily_timeout_seconds", 30.0), \
         patch.object(settings, "tavily_snippet_max_chars", 500):
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        
        results = await _web_search_impl("test query", max_results=1)
        
        # Verify snippet is truncated
        assert len(results[0]["snippet"]) <= 500
        # The current implementation just truncates without adding ellipsis
        assert "This is a very long content that exceeds the maximum allowed length." in results[0]["snippet"]


def test_web_search_args_validation():
    """Test WebSearchArgs validation."""
    # Valid args
    args = WebSearchArgs(query="test query", max_results=5)
    assert args.query == "test query"
    assert args.max_results == 5
    
    # Default max_results
    args = WebSearchArgs(query="test query")
    assert args.max_results == 5
    
    # Invalid max_results (too low)
    with pytest.raises(ValueError, match="greater_than_equal"):
        WebSearchArgs(query="test", max_results=0)
    
    # Invalid max_results (too high)
    with pytest.raises(ValueError, match="less_than_equal"):
        WebSearchArgs(query="test", max_results=21)


@pytest.mark.asyncio
async def test_web_search_empty_results():
    """Test handling of empty API response."""
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch.object(settings, "tavily_api_key", "test-api-key"), \
         patch.object(settings, "tavily_timeout_seconds", 30.0):
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = AsyncMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        
        results = await _web_search_impl("test query", max_results=5)
        assert results == []


@pytest.mark.asyncio
async def test_web_search_advanced_search_depth():
    """Test web search with advanced search depth."""
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch.object(settings, "tavily_api_key", "test-api-key"), \
         patch.object(settings, "tavily_timeout_seconds", 30.0), \
         patch.object(settings, "tavily_search_depth", "advanced"):
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = AsyncMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        
        await _web_search_impl("test query", max_results=3)
        
        # Verify advanced search depth was used
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["search_depth"] == "advanced"


@pytest.mark.asyncio
async def test_web_search_custom_timeout():
    """Test web search with custom timeout."""
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch.object(settings, "tavily_api_key", "test-api-key"), \
         patch.object(settings, "tavily_timeout_seconds", 30.0):
        
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_response = AsyncMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        
        await _web_search_impl("test query", max_results=3)
        
        # Verify custom timeout was used
        call_args = mock_client_class.call_args
        assert call_args[1]["timeout"] == 30.0