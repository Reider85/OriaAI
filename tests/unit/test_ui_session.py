"""Unit tests for llm_client.ui.session (UI-0 session state management)."""

import pytest

from llm_client.ui import session


@pytest.fixture
def state():
    return {}


@pytest.fixture(autouse=True)
def _reset_store(monkeypatch):
    monkeypatch.setattr(session, "_message_store", {})
    yield


def test_generate_session_id_is_uuid4_hex():
    sid = session.generate_session_id()
    assert len(sid) == 32
    assert set(sid) <= set("0123456789abcdef")


def test_session_id_from_params_single_value():
    assert session._session_id_from_params({"session_id": "abc123"}) == "abc123"


def test_session_id_from_params_list_value():
    assert session._session_id_from_params({"session_id": ["first", "second"]}) == "first"


def test_session_id_from_params_empty_list():
    assert session._session_id_from_params({"session_id": []}) is None


def test_session_id_from_params_missing():
    assert session._session_id_from_params({}) is None


def test_session_id_from_params_url_style_defaults():
    assert session.get_session_id_from_url({"session_id": "urlsid"}) == "urlsid"


def test_init_state_generates_new_session_on_first_run(monkeypatch, state):
    monkeypatch.setattr(session, "_session_state", lambda: state)
    monkeypatch.setattr(session, "get_session_id_from_url", lambda *a: None)
    sid = session.init_state()
    assert sid in state["current_session_id"]
    assert state["messages"] == []


def test_init_state_uses_url_session(monkeypatch, state):
    monkeypatch.setattr(session, "_session_state", lambda: state)
    monkeypatch.setattr(session, "get_session_id_from_url", lambda *a: "fixed-id")
    assert session.init_state() == "fixed-id"
    assert state["current_session_id"] == "fixed-id"


def test_init_state_restores_history_from_store(monkeypatch, state):
    session._message_store["fixed-id"] = [{"role": "user", "content": "hi", "metadata": None}]
    monkeypatch.setattr(session, "_session_state", lambda: state)
    monkeypatch.setattr(session, "get_session_id_from_url", lambda *a: "fixed-id")
    session.init_state()
    assert state["messages"] == [{"role": "user", "content": "hi", "metadata": None}]


def test_add_message_appends_and_mirrors_store(monkeypatch, state):
    monkeypatch.setattr(session, "_session_state", lambda: state)
    message = session.add_message("sid-1", "user", "hello")
    assert state["messages"] == [message]
    assert session._message_store["sid-1"] == [message]
    assert message["role"] == "user"
    assert message["content"] == "hello"
    assert "timestamp" in message
    assert message["metadata"] is None


def test_add_message_with_metadata(monkeypatch, state):
    monkeypatch.setattr(session, "_session_state", lambda: state)
    message = session.add_message("sid-1", "assistant", "hi", {"pii_score": 0.1})
    assert message["metadata"] == {"pii_score": 0.1}


def test_get_messages_returns_copy(monkeypatch, state):
    monkeypatch.setattr(session, "_session_state", lambda: state)
    session.add_message("sid-1", "user", "hello")
    messages = session.get_messages()
    messages.clear()
    assert session.get_messages() == [state["messages"][0]]


def test_clear_empties_history(monkeypatch, state):
    monkeypatch.setattr(session, "_session_state", lambda: state)
    session.add_message("sid-1", "user", "hello")
    session.clear()
    assert state["messages"] == []


def test_current_session_id_falls_back_to_new(monkeypatch, state):
    monkeypatch.setattr(session, "_session_state", lambda: state)
    sid = session.current_session_id()
    assert len(sid) == 32
