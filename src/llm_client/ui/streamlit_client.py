"""Streamlit implementation of UIClient (UI-2, ADR-002).

Concrete ``UIClient`` backed by Streamlit 1.40+.  All UI calls from the
application layer go through this class (via ``get_ui_client()``) instead of
importing ``st.*`` directly.  Streamlit-specific hooks that have no analogue
in other backends (sidebar, status badges) intentionally stay outside this
interface.

Stateful note: the class keeps its streaming state (token buffer, active
placeholder) in ``st.session_state`` under the ``streamlit_client_`` prefix to
avoid collisions with application-level keys.  Instances may be constructed
per request; the factory ``get_ui_client()`` is the intended entry point.
"""

from __future__ import annotations

from typing import Any

from llm_client.types import ArtifactRef, MessageRole
from llm_client.ui.client import UIClient

_STATE_PREFIX = "streamlit_client_"
_TOKEN_BUFFER_KEY = _STATE_PREFIX + "token_buffer"
_PLACEHOLDER_KEY = _STATE_PREFIX + "placeholder"
_CHAT_INPUT_KEY = _STATE_PREFIX + "chat_input_"


def _session_state() -> dict[str, Any]:
    """Return the Streamlit ``session_state`` dict (imported lazily)."""
    import streamlit as st

    return st.session_state  # type: ignore[return-value]


class StreamlitClient(UIClient):
    """Concrete UIClient backed by Streamlit (prompt 7)."""

    # -- render_message ---------------------------------------------------

    def render_message(
        self,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Render a single chat message with ``st.chat_message`` + markdown.

        When ``metadata`` carries a ``pii_score`` and ``role`` is ``"user"``,
        a compact PII badge is rendered after the content (ADR-014).
        """
        from llm_client.ui.render import render_message as _render_message

        _render_message(role, content, metadata)

    def render_user_message(self, content: str) -> Any:
        """Render a user message bubble and return the PII badge placeholder.

        The content renders inside ``st.chat_message("user")``; an
        ``st.empty()`` placeholder (returned to the caller) shows the live PII
        badge as soon as the backend emits the ``metadata`` event (ADR-014).
        """
        import streamlit as st

        with st.chat_message("user"):
            st.markdown(content)
            return st.empty()

    def update_pii_badge(
        self,
        slot: Any,
        pii_score: float,
        pii_entities: list[str],
        message_id: str | None = None,
    ) -> None:
        """Render the live PII badge for a user message into ``slot``.

        ``slot`` is the placeholder returned by ``render_user_message``; it is
        updated as soon as the backend emits the ``metadata`` event so the
        badge appears in <1 s (ADR-014, prompt 5 DoD). Streamlit-specific hook
        (``st.empty`` + ``st.markdown``) with no analogue in other backends —
        intentionally outside the ``UIClient`` interface, like sidebar/status.
        """
        from llm_client.ui.render import render_pii_badge as _render_pii_badge

        with slot.container():
            _render_pii_badge(pii_score, pii_entities, message_id=message_id)

    # -- render_artifact --------------------------------------------------

    def render_artifact(self, artifact: ArtifactRef) -> None:
        """Render a download button for a single artifact (ADR-008)."""
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

    # -- stream_token -----------------------------------------------------

    def stream_token(self, token: str) -> None:
        """Append one token to the current assistant response.

        Tokens accumulate in a buffer under ``streamlit_client_token_buffer``
        in ``session_state`` and the running text is flushed to a lazily
        created ``st.empty()`` placeholder on every call, so partial output is
        visible immediately without waiting for the whole stream.
        """
        import streamlit as st

        state = _session_state()

        buffer = str(state.get(_TOKEN_BUFFER_KEY, "")) + token
        state[_TOKEN_BUFFER_KEY] = buffer

        placeholder = state.get(_PLACEHOLDER_KEY)
        if placeholder is None:
            placeholder = st.empty()
            state[_PLACEHOLDER_KEY] = placeholder
        placeholder.markdown(buffer)

    def get_stream_buffer(self) -> str:
        """Return the text accumulated so far by ``stream_token``."""
        return str(_session_state().get(_TOKEN_BUFFER_KEY, ""))

    def reset_stream(self) -> None:
        """Drop the streaming buffer and placeholder after a response completes."""
        state = _session_state()
        state[_TOKEN_BUFFER_KEY] = ""
        state[_PLACEHOLDER_KEY] = None

    # -- handle_user_input ------------------------------------------------

    def handle_user_input(self) -> str | None:
        """Read the current user input via ``st.chat_input``.

        The widget key is unique per session (``streamlit_client_chat_input_
        + session id``) so switching sessions does not confuse re-runs.
        """
        import streamlit as st

        from llm_client.ui.session import current_session_id

        session_id = current_session_id()
        return st.chat_input(
            "Type your message...", key=f"{_CHAT_INPUT_KEY}{session_id}"
        )


__all__ = [
    "StreamlitClient",
    "_CHAT_INPUT_KEY",
    "_PLACEHOLDER_KEY",
    "_STATE_PREFIX",
    "_TOKEN_BUFFER_KEY",
]