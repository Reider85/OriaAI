"""Rendering helpers for the Streamlit chat UI (UI-0, ADR-002/ADR-007)."""

from __future__ import annotations

from typing import Any


def render_message(role: str, content: str) -> None:
    """Render a single chat message with ``st.chat_message`` + ``st.markdown``."""
    import streamlit as st  # type: ignore[import-untyped]

    with st.chat_message(role):
        st.markdown(content)


def render_history(messages: list[dict[str, Any]]) -> None:
    """Render stored messages from the current session, in order."""
    for message in messages:
        render_message(str(message["role"]), str(message["content"]))


def render_error(message: str) -> None:
    """Render a non-fatal error banner (backend unavailable, stream failure)."""
    import streamlit as st  # type: ignore[import-untyped]

    st.error(message)


__all__ = ["render_error", "render_history", "render_message"]
