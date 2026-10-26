"""Probe MCP Server preview (ADR-004 acceleration Phase 3).

Acts as external MCP client: calls /mcp/tools (list), then
/mcp/tools/{name} (call) for each registered tool.

Pilot criterion (ROADMAP §14.1): LLM Client in MCP Server mode
answers list_tools and call_tool from external MCP client.

Usage:
    python scripts/probe_mcp_server.py --url http://localhost:8000
"""
import argparse
import asyncio
import json
import logging
import sys

import httpx

logger = logging.getLogger(__name__)


async def probe_mcp_server(base_url: str) -> bool:
    """Returns True if MCP Server responds correctly to list_tools
    and call_tool from external client."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        try:
            # 1. Health check
            logger.info("Probing /mcp/health...")
            resp = await client.get("/mcp/health")
            if resp.status_code != 200:
                logger.error("Health check failed: %s %s", resp.status_code, resp.text)
                return False
            health = resp.json()
            logger.info("Health OK: %d tools", health["tools_count"])

            # 2. List tools
            logger.info("Probing /mcp/tools (list_tools)...")
            resp = await client.get("/mcp/tools")
            if resp.status_code != 200:
                logger.error("List tools failed: %s %s", resp.status_code, resp.text)
                return False
            tools_list = resp.json()["tools"]
            logger.info("List tools OK: %d tools", len(tools_list))
            for t in tools_list:
                logger.info("  - %s: %s", t["name"], t["description"])

            # 3. Call each tool with minimal args
            for tool in tools_list:
                name = tool["name"]
                args = get_minimal_args(name)
                logger.info("Calling /mcp/tools/%s with args: %s", name, args)
                resp = await client.post(f"/mcp/tools/{name}", json=args)
                if resp.status_code != 200:
                    logger.error("Call tool %s failed: %s %s", name,
                                resp.status_code, resp.text)
                    return False
                result = resp.json()
                if result.get("error"):
                    logger.error("Tool %s returned error: %s", name, result["error"])
                    # Don't fail probe for tool-specific errors (e.g.
                    # web_search without TAVILY_API_KEY); just log.
                    continue
                logger.info("Tool %s returned: %s", name, str(result["result"])[:100])

            # 4. Streaming endpoint probe (one tool, non-essential)
            if "web_search" in [t["name"] for t in tools_list]:
                logger.info("Probing /mcp/tools/web_search/stream (SSE)...")
                args_json = json.dumps({"query": "test", "max_results": 1})
                resp = await client.get(
                    "/mcp/tools/web_search/stream",
                    params={"args_json": args_json},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    # Verify SSE format: contains "event:" lines
                    if "event:" in resp.text:
                        logger.info("SSE streaming OK")
                    else:
                        logger.warning("SSE response missing event: lines")
                else:
                    logger.warning("SSE endpoint returned %s (non-critical)", resp.status_code)

            logger.info("✅ MCP Server preview probe PASSED")
            return True
        except httpx.ConnectError as e:
            logger.error("Connection failed: %s", e)
            return False
        except httpx.TimeoutException as e:
            logger.error("Timeout: %s", e)
            return False
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error("HTTP error: %s", e)
            return False
        except Exception as e:  # noqa: BLE001 — probe must never raise, any unexpected error means failure
            logger.error("Unexpected error: %s", e)
            return False


def get_minimal_args(tool_name: str) -> dict:
    """Minimal valid args for each known tool."""
    if tool_name == "rag_query":
        return {"query": "test", "top_k": 1}
    elif tool_name == "file_export":
        return {"filename": "test.txt", "content": "test"}
    elif tool_name == "web_search":
        return {"query": "test", "max_results": 1}
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000",
                        help="LLM Client agent-service base URL")
    args = parser.parse_args()
    success = asyncio.run(probe_mcp_server(args.url))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()