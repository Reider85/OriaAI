"""Session state management for the Streamlit chat UI (UI-0, ADR-002).

History lives in ``st.session_state["messages"]`` (a ``list[dict]`` with keys
``role``, ``content``, ``timestamp``) and is mirrored into a process-local,
in-memory registry keyed by session id so a reload with ``?session_id=X`` can
restore the current conversation (no file/DB persistence in Phase 1 — ADR-002).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

MESSAGES_KEY = "messages"
CURRENT_SESSION_KEY = "current_session_id"

_message_store: dict[str, list[dict[str, Any]]] = {}


def _session_state() -> Any:
    import streamlit as st  # type: ignore[import-untyped]

    return st.session_state


def generate_session_id() -> str:
    """Generate a fresh UUID4 session id."""
    return uuid.uuid4().hex


def _session_id_from_params(params: Any) -> str | None:
    """Extract ``session_id`` from a (possibly list-valued) query param mapping."""
    raw = params.get("session_id")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    return raw if raw else None


def get_session_id_from_url(params: Any | None = None) -> str | None:
    """Read ``?session_id=...`` from the URL query params, if present.

    ``params`` is injectable for tests; it defaults to ``st.query_params``.
    """
    if params is None:
        try:
            import streamlit as st  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("streamlit is required for the chat UI") from exc
        params = st.query_params
    return _session_id_from_params(params)


def init_state() -> str:
    """Initialise session_state and return the active session id.

    The session id comes from ``?session_id=...`` in the URL when present,
    otherwise a new UUID4 is generated. Existing in-memory history for the
    session is restored so F5 keeps the conversation within the process.
    """
    state = _session_state()
    url_sid = get_session_id_from_url()
    if CURRENT_SESSION_KEY not in state:
        state[CURRENT_SESSION_KEY] = url_sid or generate_session_id()
    if MESSAGES_KEY not in state:
        _load_messages_into_state(state[CURRENT_SESSION_KEY], state)
    elif url_sid and url_sid != state[CURRENT_SESSION_KEY]:
        state[CURRENT_SESSION_KEY] = url_sid
        _load_messages_into_state(url_sid, state)
    return str(state[CURRENT_SESSION_KEY])


def current_session_id() -> str:
    """Return the active session id from session_state."""
    state = _session_state()
    return str(state.get(CURRENT_SESSION_KEY, generate_session_id()))


def add_message(
    session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Append a message to both the live history and the in-memory registry."""
    state = _session_state()
    message = {"role": role, "content": content, "timestamp": _now_iso(), "metadata": metadata}
    if MESSAGES_KEY not in state:
        state[MESSAGES_KEY] = []
    state[MESSAGES_KEY].append(message)
    _message_store.setdefault(session_id, []).append(message)
    return message


def get_messages() -> list[dict[str, Any]]:
    """Return the active session's messages from session_state."""
    state = _session_state()
    return list(state.get(MESSAGES_KEY, []))


def clear() -> None:
    """Drop the active chat history from session_state (used by "New session")."""
    _session_state()[MESSAGES_KEY] = []


def _load_messages_into_state(session_id: str, state: Any) -> None:
    history = _message_store.get(session_id)
    state[MESSAGES_KEY] = list(history) if history else []


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()
