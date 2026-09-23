"""LLM Client — Streamlit chat entry point (UI-0, ADR-002/ADR-007).

Run with ``streamlit run src/llm_client/ui/app.py`` (or ``python -m
llm_client.ui.app``). The app talks to the agent-service exclusively through
its SSE endpoints; the backend is never called directly from here.

All rendering goes through ``UIClient`` (get_ui_client()); direct ``st.*``
calls remain only where the operation is Streamlit-specific and has no
analogue in other backends (sidebar, status badges, page config).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
from collections.abc import Callable, Iterator
from typing import Any, Literal, cast

import httpx
import streamlit as st

from llm_client.types import ArtifactRef, MessageRole
from llm_client.ui import chat, render, session, sidebar
from llm_client.ui.auto_cancel import inject_auto_cancel
from llm_client.ui.client import get_ui_client
from llm_client.ui.streamlit_client import StreamlitClient

APP_PORT_ENV = "APP_PORT"
APP_PORT_DEFAULT = "8501"
PENDING_ARTIFACTS_KEY = "pending_artifacts"
STREAM_TIMEOUT_ENV = "STREAM_TIMEOUT_SECONDS"
STREAM_TIMEOUT_DEFAULT = 60.0

ArtifactFormat = Literal["md", "txt", "pdf", "docx", "odt", "xls", "xlsx"]
_ARTIFACT_FORMATS: tuple[str, ...] = ("md", "txt", "pdf", "docx", "odt", "xls", "xlsx")


def _stream_timeout() -> float:
    """Return the end-to-end streaming timeout from the environment (60 s)."""
    return float(os.getenv(STREAM_TIMEOUT_ENV, STREAM_TIMEOUT_DEFAULT))


def _stream_with_timeout(
    session_id: str, on_metadata: Callable[[Any], None] | None = None
) -> Iterator[str]:
    """Yield stream tokens but fail with a timeout badge if nothing arrives for
    ``STREAM_TIMEOUT_SECONDS`` (anti-pattern: spinner hanging forever)."""
    deadline = time.monotonic() + _stream_timeout()
    for token in chat.stream_tokens(session_id, on_metadata=on_metadata):
        if time.monotonic() > deadline:
            raise chat.ChatStreamError(
                "Timeout (no response)", status="error", detail="Timeout (no response)"
            )
        yield token


def _on_pii_metadata(
    client: Any, user_message: dict[str, Any], pii_badge_area: Any
) -> Callable[[Any], None]:
    """Build a callback that applies an SSE ``metadata`` event (PII score).

    The badge renders into ``pii_badge_area`` immediately via the UI client
    (low latency, DoD <1 s) and the same data is stored on ``user_message``
    (shared reference in session_state + in-memory store) so subsequent
    re-renders keep it.
    """

    def on_metadata(data: Any) -> None:
        if not isinstance(data, dict):
            return
        pii_score = data.get("pii_score")
        if pii_score is None:
            return
        user_message["metadata"] = {
            "message_id": data.get("message_id"),
            "pii_score": float(pii_score),
            "pii_entities": data.get("pii_entities", []),
        }
        client.update_pii_badge(
            pii_badge_area,
            float(pii_score),
            list(data.get("pii_entities", [])),
            message_id=str(data.get("message_id") or ""),
        )

    return on_metadata


def _artifact_format(raw: Any) -> ArtifactFormat:
    """Validate an ``artifact_ready`` format against supported outputs (ADR-008)."""
    fmt = str(raw or "md").lower()
    if fmt not in _ARTIFACT_FORMATS:
        fmt = "md"
    return cast(ArtifactFormat, fmt)


def _artifact_ref(artifact: dict[str, Any]) -> ArtifactRef:
    """Build an ``ArtifactRef`` from an ``artifact_ready`` SSE payload."""
    return ArtifactRef(
        artifact_id=str(artifact.get("artifact_id") or ""),
        format=_artifact_format(artifact.get("format")),
        filename=str(artifact.get("filename") or ""),
    )


st.set_page_config(page_title="LLM Client", layout="wide")
st.title("LLM Client")

inject_auto_cancel()

client = get_ui_client()

session_id = session.init_state()

# Streamlit-specific, not in UIClient interface.
selected = sidebar.render_sidebar()
if selected is None:
    session.new_session()
    st.session_state[PENDING_ARTIFACTS_KEY] = []
    st.rerun()
elif selected != session_id:
    session.switch_session(selected)
    st.session_state[PENDING_ARTIFACTS_KEY] = []
    st.rerun()

for message in session.get_messages():
    client.render_message(
        cast(MessageRole, str(message["role"])),
        str(message["content"]),
        message.get("metadata"),
    )

for artifact in st.session_state.get(PENDING_ARTIFACTS_KEY, []):
    client.render_artifact(_artifact_ref(artifact))

prompt = client.handle_user_input()
if prompt:
    user_message = session.add_message(session_id, "user", prompt)
    # Streamlit-specific: st.empty() placeholder for the live PII badge.
    pii_badge_area = client.render_user_message(prompt)

    try:
        response = chat.send_message(session_id, prompt)
        response.raise_for_status()
    except httpx.HTTPError as exc:  # backend down -> error banner, no crash (UI-0 DoD)
        render.render_error(f"Agent service unavailable ({chat.agent_service_url()}): {exc}")
    else:
        chat.clear_pending_artifacts()
        chat.clear_pending_metadata()
        # Streamlit-specific, not in UIClient interface: status placeholder
        # wraps render_status_badge (st.status / st.error / st.warning).
        status_ph = st.empty()
        answer = ""
        try:
            with status_ph.container():
                render.render_status_badge("streaming")
            for token in _stream_with_timeout(
                session_id, on_metadata=_on_pii_metadata(client, user_message, pii_badge_area)
            ):
                answer += token
                client.stream_token(token)
        except chat.ChatStreamError as exc:
            status_ph.empty()
            render.render_status_badge(
                exc.status, exc.detail, traceback_text=traceback.format_exc()
            )
        else:
            status_ph.empty()
        # Streamlit-specific, not in UIClient interface: buffer cleanup after
        # a completed response.
        if isinstance(client, StreamlitClient):
            client.reset_stream()
        if answer:
            session.add_message(session_id, "assistant", answer)
        artifacts = chat.get_pending_artifacts()
        if artifacts:
            st.session_state[PENDING_ARTIFACTS_KEY] = artifacts
            for artifact in artifacts:
                client.render_artifact(_artifact_ref(artifact))


def app_port() -> int:
    """Return ``APP_PORT`` from the environment (default 8501)."""
    return int(os.getenv(APP_PORT_ENV, APP_PORT_DEFAULT))


if __name__ == "__main__":
    sys.exit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                __file__,
                "--server.port",
                str(app_port()),
            ]
        )
    )
