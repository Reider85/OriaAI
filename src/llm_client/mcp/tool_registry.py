"""Registry for MCP-exposed tools (ADR-004 ускорение Phase 3).

Central registry: maps tool name -> {description, args_schema,
handler}. McpServer (H-1) reads from this registry.

Architecture: ARCHITECT.md v1.3.0 §5.2.6.
TRIZ: principle #1 (separation — registration vs execution).
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExposedTool:
    name: str
    description: str
    args_schema: dict
    handler: Callable[..., Awaitable[Any]]


class ExposedToolRegistry:
    """Central registry for MCP-exposed tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ExposedTool] = {}

    def register(self, tool: ExposedTool) -> None:
        """Register an ExposedTool. Logs warning if overwriting."""
        if tool.name in self._tools:
            logger.warning("Overwriting MCP tool: %s", tool.name)
        self._tools[tool.name] = tool
        logger.info("MCP tool registered: %s", tool.name)

    def register_all(self, tools: list[ExposedTool]) -> None:
        """Register multiple tools."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> ExposedTool | None:
        """Get ExposedTool by name, or None if not registered."""
        return self._tools.get(name)

    def list_tools(self) -> list[ExposedTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def unregister(self, name: str) -> bool:
        """Unregister a tool. Returns True if was registered."""
        if name in self._tools:
            del self._tools[name]
            logger.info("MCP tool unregistered: %s", name)
            return True
        return False


_registry: ExposedToolRegistry | None = None


def get_exposed_tool_registry() -> ExposedToolRegistry:
    global _registry
    if _registry is None:
        _registry = ExposedToolRegistry()
    return _registry


def reset_exposed_tool_registry() -> None:
    """Drop the singleton so the next get_exposed_tool_registry() call
    returns a fresh registry. For test setup / isolation only."""
    global _registry
    _registry = None


async def rag_query_handler(query: str, top_k: int = 5) -> dict:
    """MCP-callable wrapper for rag_query tool."""
    from ..agent.tools.rag_query import rag_query

    return await rag_query.ainvoke({"query": query, "top_k": top_k})  # type: ignore[attr-defined]


async def file_export_handler(content: str, format: str, filename: str | None = None) -> dict:
    """MCP-callable wrapper for file_export tool."""
    from ..agent.tools.file_export import file_export

    return await file_export.ainvoke({"content": content, "format": format, "filename": filename})


async def web_search_handler(query: str, max_results: int = 5) -> list:
    """MCP-callable wrapper for web_search tool."""
    from ..agent.tools.web_search import web_search

    return await web_search.ainvoke({"query": query, "max_results": max_results})


def build_default_tools() -> list[ExposedTool]:
    """Build the 4 default MCP-exposed tools (rag_query, file_export,
    web_search, agent_run). Handler functions live at module level so tests can
    mock them without touching the registry class."""
    from ..agent.tools.file_export import FileExportArgs
    from ..agent.tools.rag_query import RagQueryArgs
    from ..agent.tools.web_search import WebSearchArgs
    from .agent_run import AgentRunArgs, agent_run_handler

    return [
        ExposedTool(
            name="rag_query",
            description="Query the LLM Client's RAG knowledge base",
            args_schema=RagQueryArgs.model_json_schema(),
            handler=rag_query_handler,
        ),
        ExposedTool(
            name="file_export",
            description="Export content as a downloadable file",
            args_schema=FileExportArgs.model_json_schema(),
            handler=file_export_handler,
        ),
        ExposedTool(
            name="web_search",
            description="Search the web via Tavily API",
            args_schema=WebSearchArgs.model_json_schema(),
            handler=web_search_handler,
        ),
        ExposedTool(
            name="agent_run",
            description="Run a long-running agent task and stream progress events (SSE)",
            args_schema=AgentRunArgs.model_json_schema(),
            # Async generator handler — streamed by McpServer (duck-typed).
            handler=agent_run_handler,  # type: ignore[arg-type]
        ),
    ]


def register_default_tools(registry: ExposedToolRegistry | None = None) -> None:
    """Register the 4 default MCP-exposed tools (rag_query,
    file_export, web_search, agent_run). Called on startup if
    mcp_server_enabled=True. Defaults to the module singleton."""
    target = registry if registry is not None else get_exposed_tool_registry()
    target.register_all(build_default_tools())
    logger.info("Registered 4 default MCP-exposed tools")
