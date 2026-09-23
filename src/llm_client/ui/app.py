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
from typing import Any, Literal, cast

import streamlit as st

from llm_client.types import ArtifactRef, MessageRole
from llm_client.ui import session, sidebar
from llm_client.ui.auto_cancel import inject_auto_cancel
from llm_client.ui.client import get_ui_client

APP_PORT_ENV = "APP_PORT"
APP_PORT_DEFAULT = "8501"
PENDING_ARTIFACTS_KEY = "pending_artifacts"

ArtifactFormat = Literal["md", "txt", "pdf", "docx", "odt", "xls", "xlsx"]
_ARTIFACT_FORMATS: tuple[str, ...] = ("md", "txt", "pdf", "docx", "odt", "xls", "xlsx")


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
    # Streaming handled inside @st.fragment — sidebar clicks do not interrupt.
    client.render_streaming_fragment(
        session_id, prompt, user_message, pii_badge_area
    )


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
