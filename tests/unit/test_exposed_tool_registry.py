"""Unit tests for ExposedToolRegistry (H-2)."""

import pytest

from src.llm_client.mcp.tool_registry import (
    ExposedTool,
    ExposedToolRegistry,
    get_exposed_tool_registry,
    register_default_tools,
    reset_exposed_tool_registry,
)


def _make_tool(name: str = "tool_a") -> ExposedTool:
    async def handler(**kwargs):
        return {"ok": True}

    return ExposedTool(
        name=name,
        description=f"desc of {name}",
        args_schema={"type": "object", "properties": {}},
        handler=handler,
    )


@pytest.fixture(autouse=True)
def _clean_singleton():
    reset_exposed_tool_registry()
    yield
    reset_exposed_tool_registry()


def test_register_tool_adds_to_registry():
    registry = ExposedToolRegistry()
    registry.register(_make_tool("test_tool"))
    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "test_tool"
    assert tools[0].description == "desc of test_tool"


def test_register_all_multiple_tools():
    registry = ExposedToolRegistry()
    registry.register_all([_make_tool("a"), _make_tool("b"), _make_tool("c")])
    assert len(registry.list_tools()) == 3
    assert registry.list_names() == ["a", "b", "c"]


def test_get_tool_by_name():
    registry = ExposedToolRegistry()
    registry.register(_make_tool("rag_query"))
    tool = registry.get("rag_query")
    assert tool is not None
    assert isinstance(tool, ExposedTool)
    assert tool.name == "rag_query"


def test_get_unknown_returns_none():
    registry = ExposedToolRegistry()
    assert registry.get("unknown") is None


def test_unregister_removes_tool():
    registry = ExposedToolRegistry()
    registry.register(_make_tool("test_tool"))
    assert registry.unregister("test_tool") is True
    assert len(registry.list_tools()) == 0
    assert registry.get("test_tool") is None


def test_unregister_unknown_returns_false():
    registry = ExposedToolRegistry()
    assert registry.unregister("unknown") is False


def test_register_default_tools_registers_4():
    register_default_tools()
    registry = get_exposed_tool_registry()
    assert len(registry.list_tools()) == 4
    assert set(registry.list_names()) == {
        "rag_query",
        "file_export",
        "web_search",
        "agent_run",
    }


def test_register_overwrite_logs_warning(caplog):
    registry = ExposedToolRegistry()
    registry.register(_make_tool("dup"))
    with caplog.at_level("WARNING"):
        registry.register(_make_tool("dup"))
    assert any("Overwriting MCP tool: dup" in r.message for r in caplog.records)
    assert len(registry.list_tools()) == 1
