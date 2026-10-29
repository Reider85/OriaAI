"""Registers LLM Client tools as MCP-callable (H-1, delegated to H-2 registry)."""

import logging

from .server import McpServer
from .tool_registry import (
    file_export_handler,
    rag_query_handler,
    web_search_handler,
)

__all__ = [
    "file_export_handler",
    "rag_query_handler",
    "register_exposed_tools",
    "web_search_handler",
]

logger = logging.getLogger(__name__)


def register_exposed_tools(server: McpServer) -> None:
    """Backward-compatible shim: register the default MCP tools on a
    McpServer via the H-2 ExposedToolRegistry."""
    from .tool_registry import register_default_tools

    register_default_tools(server.registry)
    logger.info("Registered 4 MCP exposed tools: rag_query, file_export, web_search, agent_run")
