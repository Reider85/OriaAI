"""MCP Server preview (ADR-004 ускорение Phase 3).

Exposes LLM Client capabilities (rag_query, file_export,
web_search, agent_run) as MCP tools to external clients via
FastAPI routes + SSE transport.

Full MCP Server in Phase 6: WebSocket transport + OAuth 2.0 +
signed manifests ADR-019.

Architecture: ARCHITECT.md v1.3.0 §5.2.6.
TRIZ: Standard 3.2.1 (transition to nad-system); law 4.6
(transition to nad-system); law 4.9 (dynamization — gradual
rollout).
"""

import inspect
import json
import logging

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .tool_registry import ExposedTool, ExposedToolRegistry, get_exposed_tool_registry

logger = logging.getLogger(__name__)


class McpServer:
    """MCP Server preview. Mounts /mcp/* routes on existing
    FastAPI app (Phase 1 AG-0). Tools are read from an
    ExposedToolRegistry (H-2) instead of an inline dict."""

    def __init__(self, app: FastAPI, registry: ExposedToolRegistry | None = None) -> None:
        self._app = app
        self._registry = registry or get_exposed_tool_registry()
        self._router = APIRouter(prefix="/mcp", tags=["mcp"])
        self._register_routes()

    @property
    def registry(self) -> ExposedToolRegistry:
        """The ExposedToolRegistry this server reads tools from."""
        return self._registry

    def register_tool(self, name: str, description: str, args_schema: dict, handler) -> None:
        """Register a tool as MCP-callable. handler is async
        callable taking **args, returning dict."""
        self._registry.register(
            ExposedTool(
                name=name,
                description=description,
                args_schema=args_schema,
                handler=handler,
            )
        )

    def list_tools(self) -> list[dict]:
        """Returns list of tool descriptions for /mcp/tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "args_schema": t.args_schema,
            }
            for t in self._registry.list_tools()
        ]

    def _register_routes(self) -> None:
        @self._router.get("/tools")
        async def list_tools() -> dict:
            """MCP list_tools: returns array of tool descriptions."""
            return {"tools": self.list_tools()}

        @self._router.post("/tools/{name}")
        async def call_tool(name: str, args: dict) -> dict:
            """MCP call_tool: invokes named tool with args.
            Returns {result, error?}."""
            entry = self._registry.get(name)
            if entry is None:
                raise HTTPException(404, f"Tool not found: {name}")
            try:
                result = await entry.handler(**args)
                return {"result": result, "error": None}
            except Exception as e:
                logger.exception("MCP tool %s failed", name)
                return {"result": None, "error": str(e)}

        @self._router.get("/tools/{name}/stream")
        async def call_tool_streaming(name: str, args_json: str) -> StreamingResponse:
            """SSE streaming endpoint for tool results that stream
            (e.g. agent_run). args passed as JSON query param
            (limited to 4KB; for large args use POST /tools/{name}
            with non-streaming response)."""
            entry = self._registry.get(name)
            if entry is None:
                raise HTTPException(404, f"Tool not found: {name}")
            try:
                args = json.loads(args_json)
            except json.JSONDecodeError as e:
                raise HTTPException(400, f"Invalid args JSON: {e}")

            async def event_stream():
                try:
                    # If handler is async generator, stream results
                    if inspect.isasyncgenfunction(entry.handler):
                        async for chunk in entry.handler(**args):
                            yield f"data: {json.dumps(chunk)}\n\n"
                    else:
                        # Single result, emit as one SSE event
                        result = await entry.handler(**args)
                        yield f"data: {json.dumps(result)}\n\n"
                except Exception as e:
                    logger.exception("MCP streaming tool %s failed", name)
                    error_event = {"error": str(e)}
                    yield f"data: {json.dumps(error_event)}\n\n"

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
            )

        @self._router.get("/health")
        async def health() -> dict:
            """Health check: returns server status."""
            names = self._registry.list_names()
            return {
                "status": "ok",
                "tools_count": len(names),
                "tools": names,
            }

    def mount(self) -> None:
        """Mount /mcp routes on the FastAPI app."""
        self._app.include_router(self._router)
        logger.info(
            "MCP Server preview mounted at /mcp/* with %d tools",
            len(self._registry.list_tools()),
        )
