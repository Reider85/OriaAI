"""file_export tool — persists LLM-produced content as an S3 artifact (AG-4).

``@tool``-decorated async function that writes markdown / plain-text content to
S3-compatible storage (MinIO in dev).  Slow formats (pdf / docx / odt / xls /
xlsx) are stubbed with a 2-second latency and a ``.txt`` placeholder — the
real Phase 5 background worker (ADR-018) will handle rendering.

ToolMessage return value::

    {"artifact_id": "<hex>", "format": "md", "filename": "report.md",
     "s3_key": "artifacts/<hex>/report.md"}

The SSE generator in ``service.py`` picks up ``artifact_id`` from this payload
and emits ``event: artifact_ready`` (AG-3).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal
from uuid import uuid4

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from ...storage.factory import create_file_storage
from ..artifacts import (
    FAST_FORMATS,
    STATUS_GENERATING,
    STATUS_READY,
    artifact_object_key,
    sanitize_filename,
    save_artifact_meta,
    stem_of,
)

logger = logging.getLogger(__name__)

SLOW_FORMAT_STUB_LATENCY_SECONDS = 2.0


class FileExportArgs(BaseModel):
    """Arguments for the file_export tool."""

    content: str = Field(..., description="Контент файла")
    format: Literal["md", "txt", "pdf", "docx", "odt", "xls", "xlsx"] = Field(
        ..., description="Формат файла"
    )
    filename: str | None = Field(
        default=None, description="Имя файла (без path)"
    )


@tool(args_schema=FileExportArgs)
async def file_export(content: str, format: str, filename: str | None = None) -> dict:
    """Сохраняет контент как артефакт в S3 (MinIO).

    Возвращает ``artifact_id``, ``format``, ``filename``, ``s3_key``.
    Быстрые форматы (md/txt) — синхронно.  Медленные (pdf/docx/odt/xls/xlsx) —
    асинхронно, 503 + retry (Phase 5 ADR-018 добавит real worker).
    """
    fmt = format.lower()
    safe_name = sanitize_filename(filename, fmt)
    artifact_id = uuid4().hex
    s3_key = artifact_object_key(artifact_id, safe_name)
    storage = create_file_storage()

    if fmt in FAST_FORMATS:
        content_bytes = content.encode("utf-8")
        await storage.save(content_bytes, s3_key)
        await save_artifact_meta(
            storage,
            artifact_id,
            {
                "artifact_id": artifact_id,
                "format": fmt,
                "filename": safe_name,
                "s3_key": s3_key,
                "status": STATUS_READY,
            },
        )
        logger.info(
            "file_export fast artifact id=%s format=%s size=%d",
            artifact_id,
            fmt,
            len(content_bytes),
        )
        return {
            "artifact_id": artifact_id,
            "format": fmt,
            "filename": safe_name,
            "s3_key": s3_key,
        }

    # Slow path — stub for Phase 1, real worker in Phase 5 (ADR-018).
    await asyncio.sleep(SLOW_FORMAT_STUB_LATENCY_SECONDS)

    placeholder_name = stem_of(safe_name) + ".txt"
    placeholder_key = artifact_object_key(artifact_id, placeholder_name)
    await storage.save(content.encode("utf-8"), placeholder_key)
    await save_artifact_meta(
        storage,
        artifact_id,
        {
            "artifact_id": artifact_id,
            "format": fmt,
            "filename": safe_name,
            "s3_key": placeholder_key,
            "status": STATUS_GENERATING,
        },
    )
    logger.info(
        "file_export stub artifact id=%s format=%s bytes=%d",
        artifact_id,
        fmt,
        len(content.encode()),
    )
    return {
        "artifact_id": artifact_id,
        "format": fmt,
        "filename": safe_name,
        "s3_key": placeholder_key,
        "status": STATUS_GENERATING,
    }
