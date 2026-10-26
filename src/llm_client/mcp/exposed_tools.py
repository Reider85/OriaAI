"""Registers LLM Client tools as MCP-callable (H-1)."""
import logging

from ..agent.tools.file_export import FileExportArgs, file_export
from ..agent.tools.rag_query import RagQueryArgs, rag_query
from ..agent.tools.web_search import WebSearchArgs, web_search
from .server import McpServer

logger = logging.getLogger(__name__)


async def rag_query_handler(query: str, top_k: int = 5) -> dict:
    """MCP-callable wrapper for rag_query tool."""
    result = await rag_query.ainvoke({"query": query, "top_k": top_k})
    return result


async def file_export_handler(content: str, format: str,
                               filename: str | None = None) -> dict:
    """MCP-callable wrapper for file_export tool."""
    result = await file_export.ainvoke({
        "content": content,
        "format": format,
        "filename": filename,
    })
    return result


async def web_search_handler(query: str, max_results: int = 5) -> list:
    """MCP-callable wrapper for web_search tool."""
    result = await web_search.ainvoke({"query": query, "max_results": max_results})
    return result


def register_exposed_tools(server: McpServer) -> None:
    """Register all LLM Client tools with the McpServer."""
    server.register_tool(
        name="rag_query",
        description="Query the LLM Client's RAG knowledge base",
        args_schema=RagQueryArgs.model_json_schema(),
        handler=rag_query_handler,
    )
    server.register_tool(
        name="file_export",
        description="Export content as a downloadable file",
        args_schema=FileExportArgs.model_json_schema(),
        handler=file_export_handler,
    )
    server.register_tool(
        name="web_search",
        description="Search the web via Tavily API",
        args_schema=WebSearchArgs.model_json_schema(),
        handler=web_search_handler,
    )
    logger.info("Registered 3 MCP exposed tools: rag_query, file_export, web_search")