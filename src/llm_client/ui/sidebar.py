"""Sessions sidebar for the Streamlit chat UI (UI-1, ADR-002).

The sidebar lists in-memory sessions (Phase 1 has no RedisSessionStore) and
lets the user pick one or start a fresh session. ``render_sidebar()`` returns
the selected ``session_id`` or ``None`` when "New session" was pressed so the
caller (``app.py``) decides how to react.
"""

from __future__ import annotations

from typing import Any


def _session_label(item: dict[str, Any]) -> str:
    """Human-readable sidebar label: ``"<first prompt> — <HH:MM>"``."""
    label = (item.get("first_prompt") or "").strip()[:30]
    if not label:
        label = "New session"
    created_at = item.get("created_at") or ""
    when = created_at[11:16] if len(created_at) >= 16 else created_at
    return f"{label} — {when}"


def render_sidebar() -> str | None:
    """Render the sessions sidebar inside ``@st.fragment`` (prompt 10).

    The fragment isolates re-runs so that chat streaming tokens do not cause
    the sidebar to re-render -- only explicit sidebar interactions (button
    clicks, selectbox changes) trigger a sidebar refresh.

    Returns the currently selected ``session_id`` (default: the active one), or
    ``None`` when the "New session" button was pressed. Nothing is mutated here;
    switching/creating is the caller's responsibility (see ``app.py``).
    """
    import streamlit as st  # type: ignore[import-untyped]

    from llm_client.ui import session

    @st.fragment
    def _sidebar_fragment() -> str | None:
        sessions = session.get_sessions_list()
        current = session.current_session_id()

        with st.sidebar:
            st.subheader("Sessions")
            if st.button("New session", use_container_width=True):
                return None
            if not sessions:
                st.caption("No sessions yet")
                return None
            options = [item["session_id"] for item in sessions]
            default_index = next(
                (i for i, item in enumerate(sessions) if item["session_id"] == current),
                0,
            )
            selected = st.selectbox(
                "Select session",
                options=options,
                index=default_index,
                format_func=lambda sid: _session_label(
                    next((item for item in sessions if item["session_id"] == sid), {})
                ),
            )
            st.caption(f"{len(sessions)} session{'s' if len(sessions) != 1 else ''}")
        return selected

    return _sidebar_fragment()


__all__ = ["render_sidebar"]