"""Unit tests for Phase 3 G-3 MCP Server toggle in settings panel (ADR-004)."""

from unittest.mock import MagicMock, patch

from llm_client.ui.render import render_mcp_server_toggle, render_settings_panel


def _install_checkbox(monkeypatch, return_value: bool, captured: list):
    """Replace st.checkbox with a recorder that returns ``return_value``."""
    import streamlit as st

    def mock_checkbox(*args, **kwargs):
        captured.append({"args": args, "kwargs": kwargs})
        return return_value

    monkeypatch.setattr(st, "checkbox", mock_checkbox)


def _install_button(monkeypatch, return_value: bool):
    import streamlit as st

    monkeypatch.setattr(st, "button", lambda *args, **kwargs: return_value)


def test_render_mcp_server_toggle_default_off(monkeypatch):
    """Settings.mcp_server_enabled=False → checkbox unchecked, returns False."""
    import streamlit as st

    captured = []
    _install_checkbox(monkeypatch, False, captured)
    infos = []
    monkeypatch.setattr(st, "info", lambda msg: infos.append(msg))

    session_state = {}
    with patch("llm_client.config.settings") as mock_settings:
        mock_settings.mcp_server_enabled = False
        mock_settings.mcp_server_transport = "sse"
        enabled = render_mcp_server_toggle(session_state)

    assert enabled is False
    assert session_state["settings"]["mcp_server_enabled"] is False
    # Checkbox rendered with deployment default and the G-3 widget key
    assert len(captured) == 1
    assert captured[0]["args"][0] == "Enable MCP Server (preview)"
    assert captured[0]["kwargs"].get("key") == "settings_mcp_server_enabled"
    assert captured[0]["kwargs"].get("value") is False
    # Disabled → no endpoint info
    assert infos == []


def test_render_mcp_server_toggle_user_checks(monkeypatch):
    """User checks the toggle → returns True, info message shown."""
    import streamlit as st

    captured = []
    _install_checkbox(monkeypatch, True, captured)
    infos = []
    monkeypatch.setattr(st, "info", lambda msg: infos.append(msg))
    _install_button(monkeypatch, False)

    session_state = {}
    with patch("llm_client.config.settings") as mock_settings:
        mock_settings.mcp_server_enabled = False
        mock_settings.mcp_server_transport = "sse"
        enabled = render_mcp_server_toggle(session_state)

    assert enabled is True
    assert session_state["settings"]["mcp_server_enabled"] is True
    assert len(infos) == 1


def test_render_mcp_server_toggle_shows_endpoint_url(monkeypatch):
    """When enabled, info contains the MCP endpoint URL and transport."""
    import os

    import streamlit as st

    _install_checkbox(monkeypatch, True, [])
    infos = []
    monkeypatch.setattr(st, "info", lambda msg: infos.append(msg))
    _install_button(monkeypatch, False)
    monkeypatch.setenv("AGENT_SERVICE_URL", "http://agent-host:8000")

    session_state = {}
    with patch("llm_client.config.settings") as mock_settings:
        mock_settings.mcp_server_enabled = True
        mock_settings.mcp_server_transport = "sse"
        render_mcp_server_toggle(session_state)

    info = infos[0]
    assert f"{os.environ['AGENT_SERVICE_URL']}/mcp/tools" in info
    assert "Transport: SSE" in info
    assert "rag_query, file_export, web_search" in info


def test_render_mcp_server_toggle_health_check_success(monkeypatch):
    """Health button click → GET /mcp/health, success message with tools_count."""
    import streamlit as st

    from llm_client.ui import render

    _install_checkbox(monkeypatch, True, [])
    _install_button(monkeypatch, True)
    successes = []
    errors = []
    monkeypatch.setattr(st, "success", lambda msg: successes.append(msg))
    monkeypatch.setattr(st, "error", lambda msg: errors.append(msg))
    monkeypatch.setenv("AGENT_SERVICE_URL", "http://localhost:8000")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok", "tools_count": 3}

    session_state = {}
    with (
        patch("llm_client.config.settings") as mock_settings,
        patch.object(render.httpx, "get", return_value=mock_response) as mock_get,
    ):
        mock_settings.mcp_server_enabled = True
        mock_settings.mcp_server_transport = "sse"
        render_mcp_server_toggle(session_state)

    mock_get.assert_called_once_with("http://localhost:8000/mcp/health", timeout=5.0)
    assert successes == ["OK — 3 tools registered"]
    assert errors == []


def test_render_mcp_server_toggle_health_check_failure(monkeypatch):
    """Health endpoint unreachable → st.error, no exception raised."""
    import streamlit as st

    from llm_client.ui import render

    _install_checkbox(monkeypatch, True, [])
    _install_button(monkeypatch, True)
    errors = []
    monkeypatch.setattr(st, "error", lambda msg: errors.append(msg))
    monkeypatch.setattr(st, "success", lambda msg: None)

    session_state = {}
    with (
        patch("llm_client.config.settings") as mock_settings,
        patch.object(
            render.httpx,
            "get",
            side_effect=render.httpx.ConnectError("refused"),
        ) as mock_get,
    ):
        mock_settings.mcp_server_enabled = True
        mock_settings.mcp_server_transport = "sse"
        render_mcp_server_toggle(session_state)

    mock_get.assert_called_once()
    assert len(errors) == 1
    assert "Cannot reach MCP Server" in errors[0]


def test_settings_panel_includes_mcp_server_toggle(monkeypatch):
    """render_settings_panel renders the toggle and returns mcp_server_enabled."""
    import streamlit as st

    captured = []
    original_selectbox = st.selectbox

    def mock_selectbox(*args, **kwargs):
        key = kwargs.get("key")
        if key == "settings_retrieval_strategy":
            return "hybrid"
        options = kwargs.get("options", [])
        index = kwargs.get("index", 0)
        return options[index] if options else None

    _install_checkbox(monkeypatch, True, captured)
    st.selectbox = mock_selectbox
    try:
        session_state = {}
        with patch("llm_client.config.settings") as mock_settings:
            mock_settings.mcp_server_enabled = False
            mock_settings.mcp_server_transport = "sse"
            settings = render_settings_panel(session_state)
    finally:
        st.selectbox = original_selectbox

    # Toggle widget was rendered as part of the panel
    mcp_calls = [c for c in captured if c["kwargs"].get("key") == "settings_mcp_server_enabled"]
    assert len(mcp_calls) == 1

    # Value flows into the returned settings dict (display-only; backend ignores)
    assert settings["mcp_server_enabled"] is True
    assert session_state["settings"]["mcp_server_enabled"] is True

    # Other G-1/G-2 fields unaffected
    assert "router_policy" in settings
    assert "tool_calling_mode" in settings


def test_send_message_includes_mcp_server_enabled(monkeypatch):
    """chat.send_message forwards mcp_server_enabled in the request body."""
    import httpx

    from llm_client.ui import chat

    captured_requests = []

    def mock_post(url, json=None, timeout=None):
        captured_requests.append(json)
        response = httpx.Response(202)
        response.request = httpx.Request("POST", url, json=json)
        return response

    with patch("llm_client.ui.chat.httpx.post", side_effect=mock_post):
        chat.send_message(
            session_id="test-session",
            message="test message",
            settings={"tools_enabled": ["rag_query"], "mcp_server_enabled": True},
        )

    assert len(captured_requests) == 1
    assert captured_requests[0]["settings"]["mcp_server_enabled"] is True
