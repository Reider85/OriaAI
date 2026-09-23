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

from collections.abc import Callable
from typing import Any, Literal, cast

from llm_client.types import ArtifactRef, MessageRole
from llm_client.ui.client import UIClient

_STATE_PREFIX = "streamlit_client_"
_TOKEN_BUFFER_KEY = _STATE_PREFIX + "token_buffer"
_PLACEHOLDER_KEY = _STATE_PREFIX + "placeholder"
_CHAT_INPUT_KEY = _STATE_PREFIX + "chat_input_"
_STREAMING_DONE_KEY = _STATE_PREFIX + "streaming_done"
_ANSWER_KEY = _STATE_PREFIX + "answer"
_STREAMING_PLACEHOLDER_KEY = _STATE_PREFIX + "streaming_placeholder"


def _session_state() -> dict[str, Any]:
    """Return the Streamlit ``session_state`` dict (imported lazily)."""
    import streamlit as st

    return st.session_state  # type: ignore[return-value]


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

    # -- render_chat_fragment ---------------------------------------------

    def render_chat_fragment(self, session_id: str) -> None:
        """Render chat history inside ``@st.fragment`` (prompt 9).

        The fragment isolates re-runs so sidebar interactions do not cause the
        chat area to flicker. History is read from ``session_state[session_id]``
        and rendered via ``render_message`` (which includes PII badges for user
        messages).
        """
        import streamlit as st

        @st.fragment
        def _chat_history() -> None:
            messages = st.session_state.get(session_id, {}).get("messages", [])
            for msg in messages:
                self.render_message(
                    str(msg.get("role", "user")),
                    str(msg.get("content", "")),
                    msg.get("metadata"),
                )

        _chat_history()

    # -- render_streaming_fragment ----------------------------------------

    def render_streaming_fragment(
        self,
        session_id: str,
        prompt: str,
        user_message: dict[str, Any],
        pii_badge_area: Any,
        on_pii_metadata: Callable[[Any], None] | None = None,
    ) -> None:
        """Handle the full streaming lifecycle inside ``@st.fragment`` (prompt 9).

        The fragment owns: POST to agent-service, SSE token loop, status badge,
        PII badge updates, answer storage, and artifact rendering.  Because it
        is a fragment, sidebar clicks do not interrupt an active stream — the
        fragment re-executes on page rerun but its internal state (stored in
        ``session_state``) tells it whether streaming is already complete.

        ``on_pii_metadata`` is an optional callback for live PII badge updates
        during streaming (ADR-014).  It receives the raw ``metadata`` event
        payload dict.
        """
        import traceback

        import httpx
        import streamlit as st

        from llm_client.ui import chat, render

        @st.fragment
        def _streaming() -> None:
            st_state = st.session_state

            if st_state.get(_STREAMING_DONE_KEY):
                placeholder = st_state.get(_STREAMING_PLACEHOLDER_KEY)
                answer = st_state.get(_ANSWER_KEY, "")
                if placeholder is not None and answer:
                    placeholder.markdown(answer)
                return

            st_state[_STREAMING_DONE_KEY] = False
            st_state[_ANSWER_KEY] = ""

            status_ph = st.empty()
            answer = ""

            try:
                response = chat.send_message(session_id, prompt)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                render.render_error(
                    f"Agent service unavailable ({chat.agent_service_url()}): {exc}"
                )
                st_state[_STREAMING_DONE_KEY] = True
                return

            chat.clear_pending_artifacts()
            chat.clear_pending_metadata()

            streaming_ph = st.empty()
            st_state[_STREAMING_PLACEHOLDER_KEY] = streaming_ph

            def _on_metadata(data: Any) -> None:
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
                self.update_pii_badge(
                    pii_badge_area,
                    float(pii_score),
                    list(data.get("pii_entities", [])),
                    message_id=str(data.get("message_id") or ""),
                )

            try:
                with status_ph.container():
                    render.render_status_badge("streaming")

                for token in chat.stream_tokens(
                    session_id,
                    on_metadata=on_pii_metadata if on_pii_metadata is not None else _on_metadata,
                ):
                    answer += token
                    streaming_ph.markdown(answer)

            except chat.ChatStreamError as exc:
                status_ph.empty()
                render.render_status_badge(
                    exc.status, exc.detail, traceback_text=traceback.format_exc()
                )
            else:
                status_ph.empty()

            st_state[_STREAMING_DONE_KEY] = True
            st_state[_ANSWER_KEY] = answer

            if answer:
                from llm_client.ui import session as _session

                _session.add_message(session_id, "assistant", answer)

            artifacts = chat.get_pending_artifacts()
            if artifacts:
                pending_key = "pending_artifacts"
                st_state[pending_key] = artifacts
                for artifact in artifacts:
                    self.render_artifact(_artifact_ref(artifact))

            for key in (_TOKEN_BUFFER_KEY, _PLACEHOLDER_KEY):
                st_state.pop(key, None)

        _streaming()

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
    "_ANSWER_KEY",
    "_CHAT_INPUT_KEY",
    "_PLACEHOLDER_KEY",
    "_STATE_PREFIX",
    "_STREAMING_DONE_KEY",
    "_STREAMING_PLACEHOLDER_KEY",
    "_TOKEN_BUFFER_KEY",
    "StreamlitClient",
]