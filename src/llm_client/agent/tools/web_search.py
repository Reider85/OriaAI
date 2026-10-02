"""web_search tool via Tavily API (AG-5, Phase 2).

Implements ADR-005 (Tool Layer) on a concrete web-search tool.
Architecture contract: ARCHITECT.md v1.2.0 §5.2.4 строки 435-443.
"""

import logging

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ...config import settings

logger = logging.getLogger(__name__)


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Поисковый запрос")
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max number of results to return (1-20)",
    )


async def _web_search_impl(query: str, max_results: int = 5) -> list[dict]:
    """Implementation function for web_search tool."""
    api_key = settings.tavily_api_key
    if not api_key:
        logger.error("TAVILY_API_KEY not set — web_search unavailable")
        raise RuntimeError("web_search tool requires TAVILY_API_KEY in environment")

    async with httpx.AsyncClient(timeout=settings.tavily_timeout_seconds) as client:
        response = await client.post(
            settings.tavily_api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "query": query,
                "max_results": max_results,
                "include_answer": False,  # мы хотим только results
                "search_depth": settings.tavily_search_depth,
            },
        )
        response.raise_for_status()
        data = await response.json()

    # Normalize Tavily response to our contract:
    results = []
    for r in data.get("results", [])[:max_results]:
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[: settings.tavily_snippet_max_chars],  # truncate
                "score": r.get("score"),
            }
        )

    logger.info(
        "web_search query=%r max_results=%d returned=%d",
        query,
        max_results,
        len(results),
    )
    return results


# Create and export the tool instance.
# ``tool()`` derives the exposed name from the function __name__, which would
# advertise ``_web_search_impl`` to the LLM and leak an internal symbol. Name it
# explicitly so bind_tools registers the contract name (ADR-005 Tool Layer).
web_search = StructuredTool.from_function(
    coroutine=_web_search_impl,
    name="web_search",
    description="Search the public web via Tavily and return normalized results.",
    args_schema=WebSearchArgs,
)
