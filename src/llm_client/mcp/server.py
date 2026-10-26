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
import json
import logging

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


class McpServer:
    """MCP Server preview. Mounts /mcp/* routes on existing
    FastAPI app (Phase 1 AG-0)."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._tools_registry: dict[str, dict] = {}  # name -> {tool, schema, handler}
        self._router = APIRouter(prefix="/mcp", tags=["mcp"])
        self._register_routes()

    def register_tool(self, name: str, description: str,
                       args_schema: dict, handler) -> None:
        """Register a tool as MCP-callable. handler is async
        callable taking **args, returning dict."""
        self._tools_registry[name] = {
            "name": name,
            "description": description,
            "args_schema": args_schema,
            "handler": handler,
        }
        logger.info("MCP tool registered: %s", name)

    def _register_routes(self) -> None:
        @self._router.get("/tools")
        async def list_tools() -> dict:
            """MCP list_tools: returns array of tool descriptions."""
            return {
                "tools": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "args_schema": t["args_schema"],
                    }
                    for t in self._tools_registry.values()
                ]
            }

        @self._router.post("/tools/{name}")
        async def call_tool(name: str, args: dict) -> dict:
            """MCP call_tool: invokes named tool with args.
            Returns {result, error?}."""
            if name not in self._tools_registry:
                raise HTTPException(404, f"Tool not found: {name}")
            entry = self._tools_registry[name]
            try:
                result = await entry["handler"](**args)
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
            if name not in self._tools_registry:
                raise HTTPException(404, f"Tool not found: {name}")
            try:
                args = json.loads(args_json)
            except json.JSONDecodeError as e:
                raise HTTPException(400, f"Invalid args JSON: {e}")

            entry = self._tools_registry[name]
            async def event_stream():
                try:
                    # If handler is async generator, stream results
                    import inspect
                    if inspect.isasyncgenfunction(entry["handler"]):
                        async for chunk in entry["handler"](**args):
                            yield f"data: {json.dumps(chunk)}\n\n"
                    else:
                        # Single result, emit as one SSE event
                        result = await entry["handler"](**args)
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
            return {
                "status": "ok",
                "tools_count": len(self._tools_registry),
                "tools": list(self._tools_registry.keys()),
            }

    def mount(self) -> None:
        """Mount /mcp routes on the FastAPI app."""
        self._app.include_router(self._router)
        logger.info(
            "MCP Server preview mounted at /mcp/* with %d tools",
            len(self._tools_registry),
        )