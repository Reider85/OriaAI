"""Artifact key layout and metadata sidecar for the file_export tool (AG-4).

Artifacts live in S3-compatible storage under a per-artifact prefix::

    artifacts/{artifact_id}/{filename}          # object payload
    artifacts/{artifact_id}/.artifact.json      # metadata sidecar

The sidecar carries the status (``ready`` / ``generating``) and the key of the
object that actually holds bytes, so ``GET /artifacts/{id}`` can answer 200 /
503 / 404 without a database.  Phase 1 keeps artifact metadata in S3 only — a
database for worker tracking arrives with the Phase 5 background worker
(ADR-018).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ARTIFACT_PREFIX = "artifacts"
ARTIFACT_META_NAME = ".artifact.json"
STATUS_READY = "ready"
STATUS_GENERATING = "generating"
FAST_FORMATS = ("md", "txt")
SLOW_FORMATS = ("pdf", "docx", "odt", "xls", "xlsx")


def artifact_object_key(artifact_id: str, filename: str) -> str:
    """Full S3 key for an artifact payload object."""
    return f"{ARTIFACT_PREFIX}/{artifact_id}/{filename}"


def artifact_meta_key(artifact_id: str) -> str:
    """Full S3 key for the per-artifact metadata sidecar."""
    return f"{ARTIFACT_PREFIX}/{artifact_id}/{ARTIFACT_META_NAME}"


def sanitize_filename(filename: str | None, default_format: str) -> str:
    """Return a safe, non-path-traversal filename for an artifact.

    Rules (per AG-PROMPTS prompt 5):
    - ``pathlib.Path(name).name`` strips directory separators and ``..``.
    - Empty / ``"."`` / ``".."`` names fall back to ``artifact.{format}``.
    """
    if filename:
        filename = Path(filename).name
        if not filename or filename in (".", ".."):
            filename = None
    if not filename:
        filename = f"artifact.{default_format}"
    return filename


def stem_of(filename: str) -> str:
    """Return the stem (name without final extension) of *filename*.

    ``"report.pdf"`` -> ``"report"``; ``"noext"`` -> ``"noext"``.
    """
    stem = Path(filename).stem
    return stem if stem else filename


async def save_artifact_meta(
    storage: object,
    artifact_id: str,
    meta: dict[str, object],
) -> None:
    """Persist the metadata sidecar to S3."""
    key = artifact_meta_key(artifact_id)
    body = json.dumps(meta, separators=(",", ":")).encode()
    # type: ignore[union-attr]
    await storage.save(body, key)


async def load_artifact_meta(
    storage: object,
    artifact_id: str,
) -> dict[str, object] | None:
    """Read the metadata sidecar, or ``None`` when not found."""
    key = artifact_meta_key(artifact_id)
    try:
        # type: ignore[union-attr]
        data = await storage.get(key)
        return json.loads(data)
    except (FileNotFoundError, KeyError):
        return None
