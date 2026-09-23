"""Abstract UI client interface (UI-2, ADR-002, TRIZ #16).

``UIClient`` isolates UI code from backend-specific rendering APIs.
In Phase 1 the only concrete implementation is ``StreamlitClient``; Phase 5
adds ``ChainlitClient`` without touching calling code.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

from llm_client.types import ArtifactRef, MessageRole

UI_BACKEND_ENV = "UI_BACKEND"
UI_BACKEND_DEFAULT = "streamlit"


class UIClient(ABC):
    """Port for UI rendering backends.

    Every method is backend-agnostic: callers never import Streamlit, Chainlit,
    or any other framework directly.  Extension hooks (sidebar, status badges)
    live in separate abstractions to keep this interface at exactly four
    methods.
    """

    @abstractmethod
    def render_message(
        self,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Render a single chat message.

        ``role`` is ``"user"``, ``"assistant"``, or ``"system"``.  When
        ``metadata`` carries a PII score and ``role`` is ``"user"``, the
        implementation renders a compact badge.
        """

    @abstractmethod
    def render_user_message(self, content: str) -> Any:
        """Render a user message bubble and return a PII badge placeholder.

        The returned placeholder receives the live PII badge as soon as the
        backend reports a ``metadata`` event for this message (ADR-014).
        Callers update that placeholder while the assistant stream is running;
        the badge is otherwise baked into later ``render_message`` calls.
        """

    @abstractmethod
    def render_artifact(self, artifact: ArtifactRef) -> None:
        """Render a download button for a generated artifact."""

    @abstractmethod
    def stream_token(self, token: str) -> None:
        """Append one token to the current assistant response.

        Implementations buffer internally and flush to the UI framework
        periodically so that callers can iterate a token stream without
        worrying about rendering granularity.
        """

    @abstractmethod
    def handle_user_input(self) -> str | None:
        """Read the current user input from the UI.

        Returns the user text when a message has been submitted, or ``None``
        when no input is pending.
        """


def get_ui_client() -> UIClient:
    """Return the ``UIClient`` implementation selected by ``UI_BACKEND``.

    Phase 1 only ships ``StreamlitClient``.  Any other backend value raises
    ``NotImplementedError`` so that Phase 5 can drop in a new implementation
    without breaking the factory.
    """
    backend = os.getenv(UI_BACKEND_ENV, UI_BACKEND_DEFAULT).lower()
    if backend == "streamlit":
        from llm_client.ui.streamlit_client import StreamlitClient

        return StreamlitClient()
    raise NotImplementedError(
        f"Backend {backend!r} not implemented in Phase 1. Available: streamlit"
    )


__all__ = ["UI_BACKEND_DEFAULT", "UI_BACKEND_ENV", "UIClient", "get_ui_client"]
