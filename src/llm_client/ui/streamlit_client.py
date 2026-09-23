"""Streamlit implementation of UIClient (UI-2, ADR-002).

Minimal stub required by ``get_ui_client()``.  Full implementation (rendering
logic, token buffering, ``@st.fragment`` integration) arrives in prompt 7.
"""

from __future__ import annotations

from typing import Any

from llm_client.types import ArtifactRef, MessageRole
from llm_client.ui.client import UIClient


class StreamlitClient(UIClient):
    """Concrete UIClient backed by Streamlit (prompt 7 fills in rendering)."""

    def render_message(
        self,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        import streamlit as st

        with st.chat_message(role):
            st.markdown(content)

    def render_artifact(self, artifact: ArtifactRef) -> None:
        from llm_client.ui.render import render_artifact_buttons

        render_artifact_buttons(
            [
                {
                    "artifact_id": artifact.artifact_id,
                    "format": artifact.format,
                    "filename": artifact.filename,
                    "s3_key": artifact.s3_key,
                }
            ]
        )

    def stream_token(self, token: str) -> None:
        pass

    def handle_user_input(self) -> str | None:
        import streamlit as st

        return st.chat_input("Type your message...")


__all__ = ["StreamlitClient"]
