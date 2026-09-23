"""Unit tests for llm_client.ui.streamlit_client StreamlitClient (UI-2, ADR-002)."""

import sys
import uuid

import pytest

from llm_client.types import ArtifactRef
from llm_client.ui.client import get_ui_client


class _FakeEmpty:
    def __init__(self):
        self.rendered: list[str] = []

    def markdown(self, text, unsafe_allow_html=False):
        self.rendered.append(text)


class _FakeStreamlit:
    def __init__(self):
        self.session_state: dict = {}
        self.chat_messages: list[tuple] = []
        self.markdown_calls: list[dict] = []
        self.chat_inputs: list[str] = []
        self.chat_input_return: str | None = None
        self.empties: list[_FakeEmpty] = []
        self.download_button = None
        self.marked: list[tuple] = []

    def chat_message(self, role):
        self.chat_messages.append(role)
        return _MessageContext(self)

    def markdown(self, text, unsafe_allow_html=False):
        self.markdown_calls.append({"text": text, "unsafe_allow_html": unsafe_allow_html})

    def empty(self):
        empty = _FakeEmpty()
        self.empties.append(empty)
        return empty

    def chat_input(self, prompt, key=None):
        self.chat_inputs.append((prompt, key))
        return self.chat_input_return


class _MessageContext:
    def __init__(self, fake):
        self._fake = fake

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def markdown(self, text, unsafe_allow_html=False):
        self._fake.marked.append((text, unsafe_allow_html))


@pytest.fixture
def fake_st(monkeypatch):
    fake = _FakeStreamlit()
    fake.session_state = {}
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    return fake


@pytest.fixture
def client():
    from llm_client.ui.streamlit_client import StreamlitClient

    return StreamlitClient()


def test_factory_returns_streamlit_client(monkeypatch, fake_st):
    from llm_client.ui.streamlit_client import StreamlitClient

    monkeypatch.delenv("UI_BACKEND", raising=False)
    assert isinstance(get_ui_client(), StreamlitClient)


class TestRenderMessage:
    def test_user_message_with_pii_renders_badge(self, fake_st, client, monkeypatch):
        from llm_client.ui import render

        calls: list[dict] = []

        def fake_render_message(role, content, metadata=None, low=None, high=None):
            calls.append({"role": role, "content": content, "metadata": metadata})

        monkeypatch.setattr(render, "render_message", fake_render_message)

        client.render_message(
            "user",
            "My name is John Smith",
            {"message_id": "m1", "pii_score": 0.92, "pii_entities": [{"type": "PERSON"}]},
        )
        assert calls and calls[0]["role"] == "user"
        assert calls[0]["content"] == "My name is John Smith"
        assert calls[0]["metadata"]["pii_score"] == 0.92

    def test_assistant_message_no_badge(self, fake_st, client, monkeypatch):
        from llm_client.ui import render

        calls: list[dict] = []

        def fake_render_message(role, content, metadata=None, low=None, high=None):
            calls.append({"role": role, "content": content, "metadata": metadata})

        monkeypatch.setattr(render, "render_message", fake_render_message)

        client.render_message("assistant", "hello")
        assert calls and calls[0]["role"] == "assistant"


class TestRenderArtifact:
    def test_delegates_to_render_artifact_buttons(self, fake_st, client, monkeypatch):
        from llm_client.ui import render

        rendered: list[list[dict]] = []
        monkeypatch.setattr(render, "render_artifact_buttons", lambda artifacts: rendered.append(artifacts))

        ref = ArtifactRef(
            artifact_id="art-1", format="pdf", filename="report.pdf", s3_key="k/report.pdf"
        )
        client.render_artifact(ref)
        assert len(rendered) == 1
        assert rendered[0][0]["artifact_id"] == "art-1"
        assert rendered[0][0]["format"] == "pdf"
        assert rendered[0][0]["filename"] == "report.pdf"


class TestStreamToken:
    def test_buffers_and_flushes_to_placeholder(self, fake_st, client):
        client.stream_token("Hel")
        client.stream_token("lo")
        assert client.get_stream_buffer() == "Hello"
        assert len(fake_st.empties) == 1
        assert fake_st.empties[0].rendered == ["Hel", "Hello"]

    def test_reset_clears_buffer_and_placeholder(self, fake_st, client):
        client.stream_token("abc")
        client.reset_stream()
        assert client.get_stream_buffer() == ""


class TestHandleUserInput:
    def test_unique_key_per_session(self, fake_st, client):
        sid = uuid.uuid4().hex
        fake_st.session_state = {"current_session_id": sid}
        client.handle_user_input()
        assert fake_st.chat_inputs == [("Type your message...", f"streamlit_client_chat_input_{sid}")]

    def test_returns_none_when_no_input(self, fake_st, client):
        fake_st.chat_input_return = None
        assert client.handle_user_input() is None

    def test_returns_prompt(self, fake_st, client):
        fake_st.chat_input_return = "hi"
        assert client.handle_user_input() == "hi"