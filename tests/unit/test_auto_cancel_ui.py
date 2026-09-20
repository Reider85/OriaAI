from llm_client.ui.auto_cancel import AUTO_CANCEL_JS, _quote


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
    assert "getAttribute" in AUTO_CANCEL_JS or "URLSearchParams" in AUTO_CANCEL_JS
    assert "localStorage" in AUTO_CANCEL_JS


def test_placeholder_backend_origin():
    assert "{{BACKEND_ORIGIN}}" in AUTO_CANCEL_JS


def test_quote_escapes_safely():
    assert _quote("window.location.origin") == '"window.location.origin"'
    assert _quote('a"b') == '"a\\"b"'
    assert _quote("a\\b") == '"a\\\\b"'


def test_stop_button_calls_cancel():
    assert "window.stop_llm_session" in AUTO_CANCEL_JS