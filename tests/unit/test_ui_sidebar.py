"""Unit tests for llm_client.ui.sidebar (UI-1 sessions sidebar)."""

import sys

import pytest

from llm_client.ui import session
from llm_client.ui import sidebar


class _FakeSidebar:
    def __init__(self):
        self.elements = []
        self._button_result = False
        self._selected = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def subheader(self, text):
        self.elements.append(("subheader", text))

    def button(self, label, use_container_width=False):
        self.elements.append(("button", label, use_container_width))
        return self._button_result

    def selectbox(self, label, options, index=0, format_func=None):
        self.elements.append(("selectbox", label, options, index, format_func))
        self._format_func = format_func
        return self._selected

    def caption(self, text):
        self.elements.append(("caption", text))


class _FakeStreamlit:
    def __init__(self, sidebar_box):
        self.sidebar = sidebar_box
        self.session_state = {}

    def subheader(self, text):
        self.sidebar.subheader(text)

    def button(self, label, use_container_width=False):
        return self.sidebar.button(label, use_container_width)

    def selectbox(self, label, options, index=0, format_func=None):
        return self.sidebar.selectbox(label, options, index, format_func)

    def caption(self, text):
        self.sidebar.caption(text)


@pytest.fixture
def fake_streamlit(monkeypatch):
    box = _FakeSidebar()
    fake = _FakeStreamlit(box)
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    return fake


def _sessions():
    return [
        {
            "session_id": "a",
            "first_prompt": "hello there",
            "created_at": "2026-01-01T10:00:00+00:00",
            "last_activity": "2026-01-01T10:00:00+00:00",
        },
        {
            "session_id": "b",
            "first_prompt": "second chat",
            "created_at": "2026-01-01T11:00:00+00:00",
            "last_activity": "2026-01-01T11:00:00+00:00",
        },
    ]


def test_render_sidebar_returns_selected_session(monkeypatch, fake_streamlit):
    monkeypatch.setattr(session, "get_sessions_list", _sessions)
    monkeypatch.setattr(session, "current_session_id", lambda: "a")
    fake_streamlit.sidebar._selected = "b"
    assert sidebar.render_sidebar() == "b"


def test_render_sidebar_defaults_to_current(monkeypatch, fake_streamlit):
    monkeypatch.setattr(session, "get_sessions_list", _sessions)
    monkeypatch.setattr(session, "current_session_id", lambda: "b")
    fake_streamlit.sidebar._selected = "b"
    assert sidebar.render_sidebar() == "b"
    selectbox = [e for e in fake_streamlit.sidebar.elements if e[0] == "selectbox"]
    assert selectbox[0][3] == 1  # index follows the current session


def test_render_sidebar_new_session_button(monkeypatch, fake_streamlit):
    monkeypatch.setattr(session, "get_sessions_list", _sessions)
    monkeypatch.setattr(session, "current_session_id", lambda: "a")
    fake_streamlit.sidebar._button_result = True
    assert sidebar.render_sidebar() is None


def test_render_sidebar_none_when_no_sessions(monkeypatch, fake_streamlit):
    monkeypatch.setattr(session, "get_sessions_list", lambda: [])
    monkeypatch.setattr(session, "current_session_id", lambda: "a")
    assert sidebar.render_sidebar() is None


def test_render_sidebar_formats_session_label(monkeypatch, fake_streamlit):
    sessions = [
        {
            "session_id": "long",
            "first_prompt": "hello world this is a long prompt",
            "created_at": "2026-01-01T10:23:00+00:00",
            "last_activity": "2026-01-01T10:23:00+00:00",
        }
    ]
    monkeypatch.setattr(session, "get_sessions_list", lambda: sessions)
    monkeypatch.setattr(session, "current_session_id", lambda: "long")
    fake_streamlit.sidebar._selected = "long"
    sidebar.render_sidebar()
    selectbox = [e for e in fake_streamlit.sidebar.elements if e[0] == "selectbox"]
    fmt = selectbox[0][4]
    assert fmt("long") == "hello world this is a long pro — 10:23"


def test_render_sidebar_label_falls_back_for_empty_prompt(monkeypatch, fake_streamlit):
    sessions = [
        {
            "session_id": "empty",
            "first_prompt": "",
            "created_at": "2026-01-01T09:05:00+00:00",
            "last_activity": "2026-01-01T09:05:00+00:00",
        }
    ]
    monkeypatch.setattr(session, "get_sessions_list", lambda: sessions)
    monkeypatch.setattr(session, "current_session_id", lambda: "empty")
    fake_streamlit.sidebar._selected = "empty"
    sidebar.render_sidebar()
    selectbox = [e for e in fake_streamlit.sidebar.elements if e[0] == "selectbox"]
    assert selectbox[0][4]("empty") == "New session — 09:05"