"""Rendering helpers for the Streamlit chat UI (UI-0, ADR-002/ADR-007).

Artifact download buttons (UI-1, ADR-008): ``render_artifact_buttons`` renders
one ``st.download_button`` per ``artifact_ready`` event. Fast formats (md/txt)
fetch their content synchronously via ``GET /artifacts/{id}``; slow formats
(pdf/docx/odt/xls/xlsx) render a disabled placeholder while the backend is
still generating (503) with a retry path.

PII score badge (UI-1, ADR-014): ``render_pii_badge`` renders a compact,
color-coded badge next to a user message using the ``pii_score`` /
``pii_entities`` the backend reports via the SSE ``metadata`` event.
"""

from __future__ import annotations

import html
import os
from collections.abc import Mapping, Sequence
from typing import Any, cast

import httpx

FAST_ARTIFACT_FORMATS = ("md", "txt")

PII_LOW_THRESHOLD_ENV = "PII_LOW_THRESHOLD"
PII_LOW_THRESHOLD_DEFAULT = 0.3
PII_HIGH_THRESHOLD_ENV = "PII_HIGH_THRESHOLD"
PII_HIGH_THRESHOLD_DEFAULT = 0.7

_BADGE_COLORS = {"low": "#2f9e44", "medium": "#f59f00", "high": "#e03131"}
_BADGE_LABELS = {"low": "PII: low", "medium": "PII: medium", "high": "PII: high"}

_MIME_BY_FORMAT = {
    "md": "text/markdown",
    "txt": "text/plain",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_ARTIFACT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)


def get_mime_type(fmt: str) -> str:
    """Map an artifact format to its MIME type (fallback: octet-stream)."""
    return _MIME_BY_FORMAT.get(fmt.lower(), "application/octet-stream")


def fetch_artifact_content(artifact_id: str) -> tuple[int, bytes | None]:
    """Fetch artifact bytes from ``GET /artifacts/{id}``.

    Returns ``(status_code, content)`` where content is ``None`` unless the
    status is 200. Transport failures surface as ``(0, None)``.
    """
    from llm_client.ui import chat

    url = f"{chat.agent_service_url()}/artifacts/{artifact_id}"
    try:
        response = httpx.get(url, timeout=_ARTIFACT_TIMEOUT)
    except httpx.HTTPError:
        return 0, None
    if response.status_code == 200:
        return 200, response.content
    return response.status_code, None


def render_artifact_buttons(artifacts: list[dict[str, Any]]) -> None:
    """Render one download button per artifact (ADR-008)."""
    for artifact in artifacts:
        _render_artifact_button(artifact)


def _render_artifact_button(artifact: dict[str, Any]) -> None:
    # Streamlit-specific widget rendering, imported lazily so the module stays
    # importable outside of a running Streamlit session.
    import streamlit as st

    artifact_id = str(artifact.get("artifact_id") or "")
    if not artifact_id:
        return
    fmt = str(artifact.get("format") or "").lower()
    filename = str(artifact.get("filename") or f"artifact-{artifact_id}.{fmt}")
    label = f"Download {fmt.upper() if fmt else 'artifact'}"
    mime = get_mime_type(fmt)

    status_code, content = fetch_artifact_content(artifact_id)
    if status_code == 404:
        st.warning(f"Artifact not found ({filename})")
        return
    if status_code == 200 and content is not None:
        st.download_button(label, data=content, file_name=filename, mime=mime)
        return

    # Slow path (pdf/docx/odt/xls/xlsx): still generating, non-blocking.
    if status_code == 503:
        st.warning("Still generating")
    disabled_label = f"{label} (Generating...)"
    st.download_button(disabled_label, data=b"", file_name=None, mime=mime, disabled=True)
    if st.button(f"Retry {filename}"):
        st.rerun()


def render_message(
    role: str, content: str, metadata: dict[str, Any] | None = None
) -> None:
    """Render a single chat message with ``st.chat_message`` + ``st.markdown``.

    When ``metadata`` carries a ``pii_score`` and ``role`` is ``"user"``, a
    compact PII badge is rendered after the content (ADR-014). PII badges are
    never rendered for assistant messages.
    """
    import streamlit as st

    with st.chat_message(role):
        st.markdown(content)
        if role == "user" and metadata:
            pii_score = metadata.get("pii_score")
            if pii_score is not None:
                render_pii_badge(
                    cast(float, pii_score),
                    metadata.get("pii_entities"),
                    message_id=str(metadata.get("message_id") or ""),
                )


def render_history(messages: list[dict[str, Any]]) -> None:
    """Render stored messages from the current session, in order."""
    for message in messages:
        render_message(
            str(message["role"]),
            str(message["content"]),
            message.get("metadata"),
        )


def render_error(message: str) -> None:
    """Render a non-fatal error banner (backend unavailable, stream failure)."""
    import streamlit as st

    st.error(message)


def render_status_badge(
    status: str,
    detail: str | None = None,
    traceback_text: str | None = None,
) -> None:
    """Render the LLM-call status indicator (UI-1, ADR-007/ADR-013).

    ``status`` is one of:

    * ``streaming`` — ``st.status`` spinner ``"Generating response..."``;
    * ``cancelled`` — red ``st.error`` ``"Cancelled: <detail>"`` (detail is the
      ``reason`` from the ADR-013 cancel event);
    * ``error`` — yellow ``st.warning`` ``"Error: <detail>"``; when
      ``traceback_text`` is given it goes into an expander, never inline.

    Uses ``st.status``/``st.empty`` only — never ``st.spinner`` (blocks re-run).
    The ``streaming`` badge is cleared by the caller via its placeholder.
    """
    import streamlit as st

    if status == "streaming":
        st.status("Generating response...", expanded=False)
        return
    if status == "cancelled":
        st.error("Cancelled" if detail is None else f"Cancelled: {detail}")
        return
    if status == "error":
        st.warning("Error" if detail is None else f"Error: {detail}")
        if traceback_text:
            with st.expander("Details"):
                st.code(traceback_text, language="python")
        return
    st.warning(f"Unknown status: {status}")


def pii_thresholds() -> tuple[float, float]:
    """Return ``(low, high)`` PII thresholds from the environment (ADR-014).

    ``PII_LOW_THRESHOLD`` (default 0.3) and ``PII_HIGH_THRESHOLD`` (default
    0.7) bound the low/medium/high bands. Never hardcoded in call sites.
    """
    low = float(os.getenv(PII_LOW_THRESHOLD_ENV, PII_LOW_THRESHOLD_DEFAULT))
    high = float(os.getenv(PII_HIGH_THRESHOLD_ENV, PII_HIGH_THRESHOLD_DEFAULT))
    return low, high


def pii_level(pii_score: float, low_threshold: float, high_threshold: float) -> str:
    """Map a PII score to ``low``/``medium``/``high`` (bounds inclusive)."""
    if pii_score >= high_threshold:
        return "high"
    if pii_score >= low_threshold:
        return "medium"
    return "low"


def entity_types_for_badge(
    pii_entities: Sequence[Any] | None,
) -> list[str]:
    """Normalize ``pii_entities`` (list of ``{"type": ...}`` dicts or strings)
    into a list of entity type names for the badge tooltip."""
    types: list[str] = []
    for entity in pii_entities or []:
        if isinstance(entity, Mapping):
            entity_type = entity.get("type")
            if entity_type:
                types.append(str(entity_type))
        elif isinstance(entity, str) and entity:
            types.append(entity)
    return types


def render_pii_badge(
    pii_score: float,
    pii_entities: Sequence[Any] | None = None,
    *,
    message_id: str | None = None,
    low_threshold: float | None = None,
    high_threshold: float | None = None,
) -> None:
    """Render a compact color-coded PII badge for a user message (UI-1, ADR-014).

    * ``< low``  -> green ``"PII: low"``;
    * ``low..high`` -> amber ``"PII: medium"``;
    * ``>= high`` -> red ``"PII: high"``.

    The detected entity types (e.g. ``["PERSON", "US_SSN"]``) are exposed as a
    native hover tooltip via the ``<span title=...>`` attribute, so the badge
    stays compact and never masks the original message text. Thresholds default
    to the environment (``PII_LOW_THRESHOLD`` / ``PII_HIGH_THRESHOLD``) and can
    be overridden per call for tests.
    """
    import streamlit as st

    if low_threshold is None or high_threshold is None:
        low_threshold, high_threshold = pii_thresholds()
    level = pii_level(pii_score, low_threshold, high_threshold)
    entities = entity_types_for_badge(pii_entities)
    st.markdown(
        _badge_markup(level, entities),
        unsafe_allow_html=True,
    )


def _badge_markup(level: str, entities: list[str]) -> str:
    color = _BADGE_COLORS[level]
    label = _BADGE_LABELS[level]
    title = f"Detected entities: {', '.join(entities)}" if entities else label
    escaped = html.escape(title, quote=True)
    return (
        f'<span title="{escaped}" style="background:{color};color:#fff;'
        f"padding:2px 8px;border-radius:10px;font-size:0.75em;"
        f'display:inline-block;">{label}</span>'
    )


__all__ = [
    "FAST_ARTIFACT_FORMATS",
    "PII_HIGH_THRESHOLD_ENV",
    "PII_LOW_THRESHOLD_ENV",
    "fetch_artifact_content",
    "get_mime_type",
    "render_artifact_buttons",
    "render_error",
    "render_history",
    "render_message",
    "render_pii_badge",
    "render_status_badge",
]
