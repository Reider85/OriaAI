from llm_client.ui.auto_cancel import AUTO_CANCEL_JS, _quote, inject_auto_cancel, render_stop_button


def test_js_contains_required_listeners():
    assert "visibilitychange" in AUTO_CANCEL_JS
    assert "pagehide" in AUTO_CANCEL_JS
    assert "beforeunload" in AUTO_CANCEL_JS


def test_js_uses_sendbeacon_and_fetch_keepalive():
    assert "sendBeacon" in AUTO_CANCEL_JS
    assert "keepalive: true" in AUTO_CANCEL_JS


def test_js_has_5s_debounce():
    assert "DEBOUNCE_MS = 5000" in AUTO_CANCEL_JS


def test_js_cancel_channel_and_reason():
    assert "/sessions/" in AUTO_CANCEL_JS
    assert "tab_closed" in AUTO_CANCEL_JS
    assert "user_cancelled" in AUTO_CANCEL_JS


def test_js_session_id_from_query_or_localstorage():
    assert "window.location.search.match" in AUTO_CANCEL_JS
    assert "localStorage" in AUTO_CANCEL_JS


def test_placeholder_backend_origin():
    assert "{{BACKEND_ORIGIN}}" in AUTO_CANCEL_JS


def test_quote_escapes_safely():
    assert _quote("window.location.origin") == '"window.location.origin"'
    assert _quote('a"b') == '"a\\"b"'
    assert _quote("a\\b") == '"a\\\\b"'


def test_stop_button_calls_cancel():
    assert "window.stop_llm_session" in AUTO_CANCEL_JS


def test_placeholder_session_id():
    assert "{{SESSION_ID}}" in AUTO_CANCEL_JS


def test_js_uses_text_plain_for_sendbeacon():
    assert 'type: "text/plain;charset=UTF-8"' in AUTO_CANCEL_JS


def test_inject_auto_cancel_accepts_parameters():
    # This test doesn't actually call inject_auto_cancel (requires streamlit)
    # but verifies the function signature exists
    import inspect
    sig = inspect.signature(inject_auto_cancel)
    assert "backend_origin" in sig.parameters
    assert "session_id" in sig.parameters


def test_render_stop_button_exists():
    # This test verifies the function exists (doesn't call it)
    assert callable(render_stop_button)


def test_session_id_from_location_injects_session_id():
    # Test that sessionIdFromLocation() uses injected SESSION_ID first
    js_with_session = AUTO_CANCEL_JS.replace("{{SESSION_ID}}", '"test-session-id"')
    assert 'return SESSION_ID || window.location.search.match(/session_id=([^&]+)/)?.[1] || localStorage.getItem("llm_session_id");' in js_with_session
