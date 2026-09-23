"""Rendering helpers for the Streamlit chat UI (UI-0, ADR-002/ADR-007).

Artifact download buttons (UI-1, ADR-008): ``render_artifact_buttons`` renders
one ``st.download_button`` per ``artifact_ready`` event. Fast formats (md/txt)
fetch their content synchronously via ``GET /artifacts/{id}``; slow formats
(pdf/docx/odt/xls/xlsx) render a disabled placeholder while the backend is
still generating (503) with a retry path.
"""

from __future__ import annotations

from typing import Any

import httpx

FAST_ARTIFACT_FORMATS = ("md", "txt")

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


def render_message(role: str, content: str) -> None:
    """Render a single chat message with ``st.chat_message`` + ``st.markdown``."""
    import streamlit as st

    with st.chat_message(role):
        st.markdown(content)


def render_history(messages: list[dict[str, Any]]) -> None:
    """Render stored messages from the current session, in order."""
    for message in messages:
        render_message(str(message["role"]), str(message["content"]))


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


__all__ = [
    "FAST_ARTIFACT_FORMATS",
    "fetch_artifact_content",
    "get_mime_type",
    "render_artifact_buttons",
    "render_error",
    "render_history",
    "render_message",
    "render_status_badge",
]
