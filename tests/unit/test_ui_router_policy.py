"""Unit tests for Phase 3 G-1 router policy selector in settings panel."""

from unittest.mock import patch

from llm_client.ui.render import render_router_policy, render_settings_panel


def test_render_router_policy_defaults():
    """Test render_router_policy with default values from settings."""
    session_state = {}
    
    # Mock st.selectbox to capture default index and options
    import streamlit as st
    original_selectbox = st.selectbox
    captured_calls = []
    
    def mock_selectbox(*args, **kwargs):
        captured_calls.append({
            "args": args,
            "kwargs": kwargs
        })
        # Return default value based on settings
        options = kwargs.get('options', [])
        if options:
            from llm_client.config import settings
            default_idx = options.index(settings.llm_router_default_policy) \
                if settings.llm_router_default_policy in options else 0
            return options[default_idx]
        return "cost_priority"  # fallback
    
    st.selectbox = mock_selectbox
    
    try:
        policy = render_router_policy(session_state)
        
        # Verify default policy returned
        assert policy == "cost_priority"
        
        # Verify session_state persistence
        assert session_state["settings"]["router_policy"] == "cost_priority"
        
# Verify selectbox was called with correct parameters
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["args"][0] == "LLM Router Policy"
        assert call["kwargs"].get("key") == "settings_router_policy"
        assert call["kwargs"].get("options") == ["cost_priority", "latency_priority", "quality_priority", "privacy_priority"]
        
        # Verify index matches default from settings
        assert call["kwargs"].get("index") == 0  # cost_priority is first in enum
        
    finally:
        st.selectbox = original_selectbox


def test_render_router_policy_user_selects_quality():
    """Test render_router_policy when user selects quality priority."""
    session_state = {}
    
    # Mock st.selectbox to return "quality_priority"
    import streamlit as st
    original_selectbox = st.selectbox
    
    def mock_selectbox(*args, **kwargs):
        key = kwargs.get("key")
        if key == "settings_router_policy":
            return "quality_priority"  # User selects quality
        options = kwargs.get("options", [])
        index = kwargs.get("index", 0)
        return options[index] if options else "cost_priority"
    
    st.selectbox = mock_selectbox
    
    try:
        policy = render_router_policy(session_state)
        
        # Verify user selection is returned
        assert policy == "quality_priority"
        
        # Verify session_state persistence
        assert session_state["settings"]["router_policy"] == "quality_priority"
        
    finally:
        st.selectbox = original_selectbox


def test_settings_panel_includes_router_policy():
    """Test render_settings_panel includes router_policy in returned dict."""
    session_state = {}
    
    # Mock st.selectbox for router policy to return "latency_priority"
    import streamlit as st
    original_selectbox = st.selectbox
    
    def mock_selectbox(*args, **kwargs):
        key = kwargs.get("key")
        if key == "settings_router_policy":
            return "latency_priority"
        elif key == "settings_retrieval_strategy":
            return "hybrid"
        options = kwargs.get("options", [])
        index = kwargs.get("index", 0)
        return options[index] if options else "hybrid"
    
    st.selectbox = mock_selectbox
    
    try:
        settings = render_settings_panel(session_state)
        
        # Verify router_policy is included
        assert "router_policy" in settings
        assert settings["router_policy"] == "latency_priority"
        
        # Verify other settings are still present
        assert "tools_enabled" in settings
        assert "retrieval_strategy" in settings
        assert "reranker" in settings
        assert "max_results" in settings
        assert "top_k" in settings
        
        # Verify session_state persistence
        assert session_state["settings"]["router_policy"] == "latency_priority"
        
    finally:
        st.selectbox = original_selectbox


def test_send_message_includes_router_policy():
    """Test that chat.send_message includes router_policy in request body."""
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
    
    # Mock st.selectbox in render_router_policy to return specific value
    import streamlit as st
    original_selectbox = st.selectbox
    
    def mock_selectbox(*args, **kwargs):
        key = kwargs.get("key")
        if key == "settings_router_policy":
            return "privacy_priority"
        options = kwargs.get("options", [])
        index = kwargs.get("index", 0)
        return options[index] if options else "cost_priority"
    
    st.selectbox = mock_selectbox
    
    try:
        # Mock the httpx.post call
        with patch("llm_client.ui.chat.httpx.post", side_effect=mock_post):
            # Call send_message with settings containing router_policy
            chat.send_message(
                session_id="test-session",
                message="test message",
                settings={
                    "tools_enabled": ["web_search"],
                    "router_policy": "privacy_priority"  # This should be in body
                }
            )
            
            # Verify request was captured
            assert len(captured_requests) == 1
            request_body = captured_requests[0]
            
            # Verify router_policy is in nested settings
            assert "settings" in request_body
            assert "router_policy" in request_body["settings"]
            assert request_body["settings"]["router_policy"] == "privacy_priority"
            
    finally:
        st.selectbox = original_selectbox


def test_resolve_router_policy_valid():
    """Test _resolve_router_policy helper with valid policy."""
    from llm_client.agent.service import _resolve_router_policy
    
    # Test with valid policy
    request_settings = {"router_policy": "quality_priority"}
    policy = _resolve_router_policy(request_settings)
    
    assert policy.value == "quality_priority"


def test_resolve_router_policy_missing():
    """Test _resolve_router_policy helper with missing policy (fallback to global)."""
    from unittest.mock import patch

    from llm_client.agent.service import _resolve_router_policy
    from llm_client.config import settings
    
    with patch.object(settings, 'llm_router_default_policy', 'latency_priority'):
        # Test with missing policy
        request_settings = {}  # No router_policy
        policy = _resolve_router_policy(request_settings)
        
        assert policy.value == "latency_priority"


def test_resolve_router_policy_invalid():
    """Test _resolve_router_policy helper with invalid policy (fallback to global)."""
    from unittest.mock import patch

    from llm_client.agent.service import _resolve_router_policy
    from llm_client.config import settings
    
    with patch.object(settings, 'llm_router_default_policy', 'privacy_priority'):
        # Test with invalid policy
        request_settings = {"router_policy": "invalid_policy"}
        policy = _resolve_router_policy(request_settings)
        
        assert policy.value == "privacy_priority"  # Falls back to global default