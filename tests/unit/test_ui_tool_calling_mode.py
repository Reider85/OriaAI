"""Unit tests for Phase 3 G-2 tool calling mode selector in settings panel."""

from unittest.mock import patch

from llm_client.ui.render import render_settings_panel, render_tool_calling_mode


def test_render_tool_calling_mode_default_auto():
    """Test render_tool_calling_mode defaults to 'auto' (index=0)."""
    session_state = {}

    # Mock st.selectbox to capture default index and options
    import streamlit as st

    original_selectbox = st.selectbox
    captured_calls = []

    def mock_selectbox(*args, **kwargs):
        captured_calls.append({"args": args, "kwargs": kwargs})
        # Return default value (index=0)
        options = kwargs.get("options", [])
        index = kwargs.get("index", 0)
        return options[index] if options else "auto"

    st.selectbox = mock_selectbox

    try:
        mode = render_tool_calling_mode(session_state)

        # Verify default mode returned
        assert mode == "auto"

        # Verify session_state persistence
        assert session_state["settings"]["tool_calling_mode"] == "auto"

        # Verify selectbox was called with correct parameters
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["args"][0] == "Tool Calling Mode"
        assert call["kwargs"].get("key") == "settings_tool_calling_mode"
        assert call["kwargs"].get("options") == ["auto", "native", "react", "hybrid"]

        # Verify index matches default (auto)
        assert call["kwargs"].get("index") == 0

    finally:
        st.selectbox = original_selectbox


def test_render_tool_calling_mode_user_selects_react():
    """Test render_tool_calling_mode when user selects react."""
    session_state = {}

    # Mock st.selectbox to return "react"
    import streamlit as st

    original_selectbox = st.selectbox

    def mock_selectbox(*args, **kwargs):
        key = kwargs.get("key")
        if key == "settings_tool_calling_mode":
            return "react"  # User selects react
        options = kwargs.get("options", [])
        index = kwargs.get("index", 0)
        return options[index] if options else "auto"

    st.selectbox = mock_selectbox

    try:
        mode = render_tool_calling_mode(session_state)

        # Verify user selection is returned
        assert mode == "react"

        # Verify session_state persistence
        assert session_state["settings"]["tool_calling_mode"] == "react"

    finally:
        st.selectbox = original_selectbox


def test_settings_panel_includes_tool_calling_mode():
    """Test render_settings_panel includes tool_calling_mode in returned dict (None if auto)."""
    session_state = {}

    # Mock st.selectbox for tool calling mode (default auto) and router policy
    import streamlit as st

    original_selectbox = st.selectbox

    def mock_selectbox(*args, **kwargs):
        key = kwargs.get("key")
        if key == "settings_retrieval_strategy":
            return "hybrid"
        options = kwargs.get("options", [])
        index = kwargs.get("index", 0)
        return options[index] if options else None

    st.selectbox = mock_selectbox

    try:
        settings = render_settings_panel(session_state)

        # Verify tool_calling_mode is included; auto converts to None
        assert "tool_calling_mode" in settings
        assert settings["tool_calling_mode"] is None

        # Verify other settings are still present
        assert "tools_enabled" in settings
        assert "retrieval_strategy" in settings
        assert "reranker" in settings
        assert "max_results" in settings
        assert "top_k" in settings
        assert "router_policy" in settings

        # Verify session_state stores the converted value (panel overwrites
        # the settings dict at the end, same pattern as router_policy)
        assert session_state["settings"]["tool_calling_mode"] is None

    finally:
        st.selectbox = original_selectbox


def test_settings_panel_includes_selected_tool_calling_mode():
    """Test render_settings_panel passes through explicit mode (react -> 'react')."""
    session_state = {}

    import streamlit as st

    original_selectbox = st.selectbox

    def mock_selectbox(*args, **kwargs):
        key = kwargs.get("key")
        if key == "settings_tool_calling_mode":
            return "react"
        if key == "settings_retrieval_strategy":
            return "hybrid"
        options = kwargs.get("options", [])
        index = kwargs.get("index", 0)
        return options[index] if options else None

    st.selectbox = mock_selectbox

    try:
        settings = render_settings_panel(session_state)

        assert settings["tool_calling_mode"] == "react"
        assert session_state["settings"]["tool_calling_mode"] == "react"

    finally:
        st.selectbox = original_selectbox


def test_send_message_includes_tool_calling_mode():
    """Test that chat.send_message includes tool_calling_mode in request body."""
    import httpx

    from llm_client.ui import chat

    # Mock httpx.post to capture request body
    captured_requests = []

    def mock_post(url, json=None, timeout=None):
        captured_requests.append(json)
        # Return mock response
        response = httpx.Response(202)
        response.request = httpx.Request("POST", url, json=json)
        return response

    try:
        # Mock the httpx.post call
        with patch("llm_client.ui.chat.httpx.post", side_effect=mock_post):
            # Explicit mode — string passed through
            chat.send_message(
                session_id="test-session",
                message="test message",
                settings={"tools_enabled": ["rag_query"], "tool_calling_mode": "react"},
            )
            # Auto mode — None passed through
            chat.send_message(
                session_id="test-session",
                message="test message",
                settings={"tools_enabled": ["rag_query"], "tool_calling_mode": None},
            )

            # Verify requests were captured
            assert len(captured_requests) == 2

            # Verify explicit mode is in nested settings
            assert "settings" in captured_requests[0]
            assert captured_requests[0]["settings"]["tool_calling_mode"] == "react"

            # Verify auto (None) is in nested settings (JSON null)
            assert "settings" in captured_requests[1]
            assert captured_requests[1]["settings"]["tool_calling_mode"] is None

    finally:
        pass
