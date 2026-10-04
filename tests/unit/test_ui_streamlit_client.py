"""Unit tests for llm_client.ui.streamlit_client StreamlitClient (UI-2, ADR-002)."""

import sys
import uuid

import pytest

from llm_client.types import ArtifactRef
from llm_client.ui.client import get_ui_client


class _FakeEmpty:
    def __init__(self):
        self.rendered: list[str] = []
        self.containers: list[int] = []
        self.cleared = 0
        self.children: list[_FakeEmpty] = []

    def markdown(self, text, unsafe_allow_html=False):
        self.rendered.append(text)

    def empty(self):
        child = _FakeEmpty()
        self.children.append(child)
        return child

    def container(self):
        self.containers.append(1)
        return _MessageContext(self)

    def clear(self):
        self.cleared += 1


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
        self.expander_calls: list[dict] = []
        self.json_calls: list[dict] = []
        self.spinner_calls: list[str] = []
        self.success_calls: str | None = None
        self.errors: list[str] = []
        self.progress_calls: list[dict] = []
        self.caption_calls: list[str] = []
        self.fragments: list[str] = []

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

    # Streamlit surface used by the streaming fragment and render helpers.
    def fragment(self, func):
        self.fragments.append(func.__name__)
        return func

    def status(self, label, expanded=None):
        return _MessageContext(self)

    def expander(self, label, expanded=False):
        self.expander_calls.append({"label": label, "expanded": expanded})
        return _MessageContext(self)

    def json(self, data):
        self.json_calls.append(data)

    def spinner(self, text):
        self.spinner_calls.append(text)
        return _MessageContext(self)

    def success(self, text):
        self.success_calls = text

    def error(self, text):
        self.errors.append(text)

    def warning(self, text):
        pass

    def caption(self, text):
        self.caption_calls.append(text)

    def progress(self, value, text=None):
        self.progress_calls.append({"value": value, "text": text})

    def metric(self, label, value):
        pass

    def divider(self):
        pass

    def code(self, text, language=None):
        pass

    def button(self, label):
        return False

    def download_button(self, *args, **kwargs):
        return False

    def rerun(self):
        raise _FakeRerun()


class _MessageContext:
    def __init__(self, fake):
        self._fake = fake

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def markdown(self, text, unsafe_allow_html=False):
        self._fake.marked.append((text, unsafe_allow_html))


class _FakeRerun(Exception):
    pass


class _FakeResponse:
    def raise_for_status(self) -> None:
        pass


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
        monkeypatch.setattr(
            render, "render_artifact_buttons", lambda artifacts: rendered.append(artifacts)
        )

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
        assert fake_st.chat_inputs == [
            ("Type your message...", f"streamlit_client_chat_input_{sid}")
        ]

    def test_returns_none_when_no_input(self, fake_st, client):
        fake_st.chat_input_return = None
        assert client.handle_user_input() is None

    def test_returns_prompt(self, fake_st, client):
        fake_st.chat_input_return = "hi"
        assert client.handle_user_input() == "hi"


class TestStreamingFragmentToolEvents:
    """G-1..G-3 wiring: the fragment must consume tool events from the stream.

    ``handle_tool_event`` used to be dead code — the stream buffered the events
    and nothing ever rendered them, so no preview, citations panel or web
    results panel could appear in the app.
    """

    @staticmethod
    def _install_stream(monkeypatch, events, tokens=("hi",)):
        from llm_client.ui import chat

        monkeypatch.setattr(chat, "send_message", lambda *a, **k: _FakeResponse())

        def fake_stream_tokens(session_id, on_metadata=None, *, on_tool_event=None):
            for event_type, data in events:
                if on_tool_event is not None:
                    on_tool_event(event_type, data)
            yield from tokens

        monkeypatch.setattr(chat, "stream_tokens", fake_stream_tokens)
        return chat

    def test_renders_tool_call_and_result_live(self, fake_st, client, monkeypatch):
        self._install_stream(
            monkeypatch,
            [
                (
                    "tool_call",
                    {
                        "tool_call_id": "tc1",
                        "tool_name": "web_search",
                        "args": {"query": "python"},
                    },
                ),
                (
                    "tool_result",
                    {
                        "tool_call_id": "tc1",
                        "preview": {"snippet_count": 1},
                        "full_results": [{"title": "T", "url": "https://e.org", "snippet": "s"}],
                    },
                ),
            ],
        )

        client.render_streaming_fragment(
            "sid-1", "hello", {"role": "user", "content": "hello"}, None
        )

        labels = [call["label"] for call in fake_st.expander_calls]
        assert "🔧 web_search — running" in labels
        assert "🔧 web_search — done" in labels
        assert "\U0001f310 Web search results (1)" in labels

    def test_records_pending_tool_calls_in_session_state(self, fake_st, client, monkeypatch):
        from llm_client.ui.streamlit_client import PENDING_TOOL_CALLS_KEY

        self._install_stream(
            monkeypatch,
            [
                (
                    "tool_call",
                    {
                        "tool_call_id": "tc1",
                        "tool_name": "rag_query",
                        "args": {"query": "error"},
                    },
                ),
                (
                    "retrieved_docs",
                    {
                        "tool_call_id": "tc1",
                        "chunk_count": 1,
                        "top_score": 0.9,
                        "source_uris": ["s3://docs/a.pdf"],
                        "chunks": [{"source_uri": "s3://docs/a.pdf", "score": 0.9}],
                    },
                ),
            ],
        )

        client.render_streaming_fragment(
            "sid-1", "hello", {"role": "user", "content": "hello"}, None
        )

        pending = fake_st.session_state[PENDING_TOOL_CALLS_KEY]
        assert pending["tc1"]["status"] == "done"
        assert pending["tc1"]["result_preview"]["chunk_count"] == 1
        assert pending["tc1"]["result_preview"]["top_score"] == 0.9
        assert pending["tc1"]["chunks"] == [{"source_uri": "s3://docs/a.pdf", "score": 0.9}]
        assert "📚 RAG citations (1 chunks)" in [call["label"] for call in fake_st.expander_calls]

    def test_rerun_restores_tool_previews(self, fake_st, client, monkeypatch):
        self._install_stream(
            monkeypatch,
            [
                (
                    "tool_call",
                    {
                        "tool_call_id": "tc1",
                        "tool_name": "web_search",
                        "args": {"query": "python"},
                    },
                ),
                (
                    "tool_result",
                    {
                        "tool_call_id": "tc1",
                        "preview": {"snippet_count": 1},
                        "full_results": [{"title": "T", "url": "https://e.org", "snippet": "s"}],
                    },
                ),
            ],
        )

        client.render_streaming_fragment(
            "sid-1", "hello", {"role": "user", "content": "hello"}, None
        )
        fake_st.expander_calls.clear()

        client.render_streaming_fragment(
            "sid-1", "hello", {"role": "user", "content": "hello"}, None
        )

        labels = [call["label"] for call in fake_st.expander_calls]
        assert "🔧 web_search — done" in labels
        assert "\U0001f310 Web search results (1)" in labels

    def test_clears_tool_event_buffer_before_each_stream(self, fake_st, client, monkeypatch):
        def _spy(name, cleared):
            def _clear():
                cleared.append(name)

            return _clear

        chat = self._install_stream(monkeypatch, [])
        cleared: list[str] = []
        for name in (
            "clear_pending_artifacts",
            "clear_pending_metadata",
            "clear_pending_tool_events",
        ):
            monkeypatch.setattr(chat, name, _spy(name, cleared))

        client.render_streaming_fragment(
            "sid-1", "hello", {"role": "user", "content": "hello"}, None
        )
        assert "clear_pending_tool_events" in cleared
