"""Shared domain types for the LLM client (UI-2, ADR-002)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MessageRole = Literal["user", "assistant", "system"]


class ArtifactRef(BaseModel):
    """Reference to a generated artifact returned by the agent-service.

    ``format`` is restricted to the seven output formats the pipeline
    supports (UI-0, ADR-008).  ``s3_key`` stores the object path in
    S3-compatible storage (MinIO in dev, AWS S3 in prod).
    """

    artifact_id: str
    format: Literal["md", "txt", "pdf", "docx", "odt", "xls", "xlsx"]
    filename: str
    s3_key: str = Field(default="", description="Object key in S3-compatible storage")


__all__ = ["ArtifactRef", "MessageRole"]
