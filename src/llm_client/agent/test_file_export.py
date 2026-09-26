"""Tests for AG-4 file_export tool, artifacts helpers, and GET /artifacts endpoint."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from llm_client.agent.artifacts import (
    STATUS_GENERATING,
    STATUS_READY,
    artifact_object_key,
    load_artifact_meta,
    sanitize_filename,
    save_artifact_meta,
    stem_of,
)
from llm_client.agent.graph import build_agent_graph
from llm_client.agent.tools import file_export
from tests.conftest import InMemoryFileStorage

# ── Helpers ───────────────────────────────────────────────────────────────────


class ToolCallingFakeLLM(FakeListChatModel):
    """Fake LLM that returns a tool_call on the first ainvoke, then plain text.

    Supports ``bind_tools`` so the graph wires up the tool_executor node.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bound_tools: list[Any] | None = None
        self._call_count: int = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> ToolCallingFakeLLM:
        self._bound_tools = tools
        return self

    async def ainvoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        self._call_count += 1
        if self._call_count == 1 and self._bound_tools:
            tool = self._bound_tools[0]
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": tool.name,
                        "args": {"content": "hello world", "format": "md"},
                        "id": "call_test_1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="Here is your file")


def _initial_state(**overrides: Any) -> dict[str, Any]:
    defaults = {
        "messages": [HumanMessage("save hello as markdown")],
        "user_id": "u1",
        "session_id": "s1",
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "iteration": 0,
        "max_iterations": 10,
        "final_answer": None,
    }
    defaults.update(overrides)
    return defaults


# ── sanitize_filename tests ──────────────────────────────────────────────────


def test_sanitize_filename_normal():
    assert sanitize_filename("report.md", "md") == "report.md"


def test_sanitize_filename_path_traversal():
    assert sanitize_filename("../../../etc/passwd", "md") == "passwd"


def test_sanitize_filename_none_falls_back():
    assert sanitize_filename(None, "txt") == "artifact.txt"


def test_sanitize_filename_dot_only():
    assert sanitize_filename(".", "md") == "artifact.md"


def test_sanitize_filename_dotdot():
    assert sanitize_filename("..", "md") == "artifact.md"


def test_sanitize_filename_empty_string():
    assert sanitize_filename("", "pdf") == "artifact.pdf"


def test_sanitize_filename_windows_backslash():
    assert sanitize_filename("..\\..\\windows\\system32", "md") == "system32"


# ── stem_of tests ────────────────────────────────────────────────────────────


def test_stem_of_normal():
    assert stem_of("report.pdf") == "report"


def test_stem_of_no_ext():
    assert stem_of("noext") == "noext"


def test_stem_of_multiple_dots():
    assert stem_of("my.file.name.md") == "my.file.name"


# ── file_export tool tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_export_md():
    storage = InMemoryFileStorage()
    with patch("llm_client.agent.tools.file_export.create_file_storage", return_value=storage):
        result = await file_export.ainvoke(
            {"content": "hello world", "format": "md"}
        )

    assert isinstance(result, dict)
    assert result["format"] == "md"
    assert result["filename"] == "artifact.md"
    assert result["s3_key"].startswith("artifacts/")
    assert result["artifact_id"]

    # Verify S3 object exists
    data = await storage.get(result["s3_key"])
    assert data == b"hello world"

    # Verify metadata sidecar exists
    meta = await load_artifact_meta(storage, result["artifact_id"])
    assert meta is not None
    assert meta["status"] == STATUS_READY
    assert meta["s3_key"] == result["s3_key"]


@pytest.mark.asyncio
async def test_file_export_txt():
    storage = InMemoryFileStorage()
    with patch("llm_client.agent.tools.file_export.create_file_storage", return_value=storage):
        result = await file_export.ainvoke(
            {"content": "plain text", "format": "txt"}
        )

    assert result["format"] == "txt"
    assert result["filename"] == "artifact.txt"
    assert result["s3_key"].endswith(".txt")


@pytest.mark.asyncio
async def test_file_export_custom_filename():
    storage = InMemoryFileStorage()
    with patch("llm_client.agent.tools.file_export.create_file_storage", return_value=storage):
        result = await file_export.ainvoke(
            {"content": "data", "format": "md", "filename": "report.md"}
        )

    assert result["filename"] == "report.md"
    assert "report.md" in result["s3_key"]


@pytest.mark.asyncio
async def test_file_export_pdf_stub():
    storage = InMemoryFileStorage()
    with patch("llm_client.agent.tools.file_export.create_file_storage", return_value=storage):
        start = time.monotonic()
        result = await file_export.ainvoke(
            {"content": "pdf content", "format": "pdf"}
        )
        elapsed = time.monotonic() - start

    assert result["format"] == "pdf"
    assert result["filename"] == "artifact.pdf"
    assert result["status"] == STATUS_GENERATING
    assert result["s3_key"].endswith(".txt")  # placeholder
    assert elapsed >= 1.9  # stub latency

    # Metadata shows generating status
    meta = await load_artifact_meta(storage, result["artifact_id"])
    assert meta is not None
    assert meta["status"] == STATUS_GENERATING


@pytest.mark.asyncio
async def test_file_export_path_traversal():
    storage = InMemoryFileStorage()
    with patch("llm_client.agent.tools.file_export.create_file_storage", return_value=storage):
        result = await file_export.ainvoke(
            {"content": "content", "format": "md", "filename": "../../../etc/passwd"}
        )

    # Path traversal stripped: Path("../../../etc/passwd").name == "passwd"
    assert result["filename"] == "passwd"
    assert ".." not in result["s3_key"]
    assert "etc" not in result["s3_key"]


# ── Graph integration test ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_with_file_export():
    """Full graph loop: planner -> tool_executor -> planner -> final_answer."""
    storage = InMemoryFileStorage()
    with patch("llm_client.agent.tools.file_export.create_file_storage", return_value=storage):
        llm = ToolCallingFakeLLM(responses=["unused"])
        graph = build_agent_graph(llm, tools=[file_export])

        chunks = []
        async for chunk in graph.astream(_initial_state()):
            chunks.append(chunk)

    # Verify graph completed
    final_chunks = [c for c in chunks if "final_answer" in c]
    assert len(final_chunks) >= 1
    assert final_chunks[-1]["final_answer"]["final_answer"] == "Here is your file"

    # Verify tool_executor ran (planner -> tool_executor -> planner -> final_answer)
    tool_chunks = [c for c in chunks if "tool_executor" in c]
    assert len(tool_chunks) >= 1

    # Verify ToolMessage in tool_executor output
    tool_chunk = tool_chunks[0]
    tool_msgs = tool_chunk["tool_executor"]["messages"]
    assert any(
        hasattr(m, "tool_call_id") for m in tool_msgs if hasattr(m, "tool_call_id")
    )


# ── GET /artifacts endpoint tests ────────────────────────────────────────────


def _create_artifact_test_app(storage: InMemoryFileStorage):
    """Minimal FastAPI app with just the artifact route for testing."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse, Response

    from llm_client.agent.artifacts import load_artifact_meta

    _MIME_BY_EXT = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
    }

    app = FastAPI()

    @app.get("/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str):
        meta = await load_artifact_meta(storage, artifact_id)
        if meta is None:
            return JSONResponse({"error": "Not found"}, status_code=404)
        if meta.get("status") == STATUS_GENERATING:
            return JSONResponse({"status": "generating"}, status_code=503)
        s3_key = meta.get("s3_key", "")
        if not s3_key:
            return JSONResponse({"error": "Invalid metadata"}, status_code=404)
        try:
            content = await storage.get(s3_key)
        except FileNotFoundError:
            return JSONResponse({"error": "Data not found"}, status_code=404)
        from pathlib import Path

        ext = Path(s3_key).suffix.lower()
        media_type = _MIME_BY_EXT.get(ext, "application/octet-stream")
        return Response(content=content, media_type=media_type)

    return app


@pytest.mark.asyncio
async def test_get_artifact_ready():
    storage = InMemoryFileStorage()
    # Save a fast-format artifact directly
    artifact_id = "test_ready_id"
    s3_key = artifact_object_key(artifact_id, "report.md")
    await storage.save(b"# Hello", s3_key)
    await save_artifact_meta(
        storage,
        artifact_id,
        {
            "artifact_id": artifact_id,
            "format": "md",
            "filename": "report.md",
            "s3_key": s3_key,
            "status": STATUS_READY,
        },
    )

    app = _create_artifact_test_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/artifacts/{artifact_id}")

    assert resp.status_code == 200
    assert resp.content == b"# Hello"
    assert "text/markdown" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_get_artifact_generating():
    storage = InMemoryFileStorage()
    artifact_id = "test_gen_id"
    s3_key = artifact_object_key(artifact_id, "report.txt")
    await storage.save(b"placeholder", s3_key)
    await save_artifact_meta(
        storage,
        artifact_id,
        {
            "artifact_id": artifact_id,
            "format": "pdf",
            "filename": "report.pdf",
            "s3_key": s3_key,
            "status": STATUS_GENERATING,
        },
    )

    app = _create_artifact_test_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/artifacts/{artifact_id}")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_get_artifact_not_found():
    app = _create_artifact_test_app(InMemoryFileStorage())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/artifacts/nonexistent_id")

    assert resp.status_code == 404
