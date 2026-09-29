"""Unit tests for llm_client.ui.render artifact download buttons (UI-1, ADR-008)."""

import sys

import pytest

from llm_client.ui import render


class _FakeDownloadButton:
    def __init__(self):
        self.calls = []

    def __call__(self, label, data=None, file_name=None, mime=None, disabled=False):
        self.calls.append(
            {
                "label": label,
                "data": data,
                "file_name": file_name,
                "mime": mime,
                "disabled": disabled,
            }
        )
        return not disabled


class _FakeStreamlit:
    def __init__(self):
        self.download_button = _FakeDownloadButton()
        self.warnings = []
        self.buttons = []
        self.errors = []
        self.status_calls = []
        self.expander_calls = []
        self.code_calls = []
        self.markdown_calls = []
        self.chat_messages = []
        self.json_calls = []
        self.spinner_calls = []
        self.caption_calls = []
        self.progress_calls = []
        self.metric_calls = []
        self.divider_calls = []
        self.fragments = []
        self._button_clicked = False

    def warning(self, text):
        self.warnings.append(text)

    def error(self, text):
        self.errors.append(text)

    def status(self, label, expanded=None):
        self.status_calls.append({"label": label, "expanded": expanded})
        return _FakeStatus()

    def expander(self, label, expanded=False):
        self.expander_calls.append({"label": label, "expanded": expanded})
        return _FakeExpander()

    def fragment(self, func):
        self.fragments.append(func.__name__)
        return func

    def code(self, text, language=None):
        self.code_calls.append({"text": text, "language": language})

    def button(self, label):
        self.buttons.append(label)
        return self._button_clicked

    def markdown(self, text, unsafe_allow_html=False):
        self.markdown_calls.append({"text": text, "unsafe_allow_html": unsafe_allow_html})

    def json(self, data):
        """Mock st.json method."""
        self.json_calls.append(data)

    def caption(self, text):
        """Mock st.caption method."""
        self.caption_calls.append(text)

    def progress(self, value, text=None):
        """Mock st.progress method."""
        self.progress_calls.append({"value": value, "text": text})

    def metric(self, label, value):
        """Mock st.metric method."""
        self.metric_calls.append({"label": label, "value": value})

    def divider(self):
        """Mock st.divider method."""
        self.divider_calls.append(True)

    def chat_message(self, role):
        self.chat_messages.append(role)
        return _FakeContainer()

    def rerun(self):
        raise _FakeRerun()

    def render_tool_call(self, tool_name, args, status="running", result_preview=None):
        """Mock render_tool_call method."""
        self.tool_call_rendered = {
            "tool_name": tool_name,
            "args": args,
            "status": status,
            "result_preview": result_preview
        }

    def spinner(self, text):
        """Mock st.spinner method."""
        self.spinner_calls.append(text)
        self.spinner_text = text
        return _FakeContextManager()

    def success(self, text):
        """Mock st.success method."""
        self.success_calls = text


class _FakeStatus:
    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class _FakeExpander:
    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class _FakeContainer:
    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class _FakeContextManager:
    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class _FakeRerun(Exception):
    pass


@pytest.fixture
def fake_streamlit(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    return fake


def test_get_mime_type_maps_formats():
    assert render.get_mime_type("md") == "text/markdown"
    assert render.get_mime_type("txt") == "text/plain"
    assert render.get_mime_type("pdf") == "application/pdf"
    assert render.get_mime_type("docx").startswith("application/vnd")
    assert render.get_mime_type("odt").startswith("application/vnd")
    assert render.get_mime_type("xls") == "application/vnd.ms-excel"
    assert render.get_mime_type("xlsx").startswith("application/vnd")
    assert render.get_mime_type("unknown") == "application/octet-stream"
    assert render.get_mime_type("PDF") == "application/pdf"


def test_fetch_artifact_content_200(monkeypatch):
    class Response:
        status_code = 200
        content = b"# hello"

    monkeypatch.setattr(render.httpx, "get", lambda *a, **k: Response())
    status, content = render.fetch_artifact_content("art-1")
    assert status == 200
    assert content == b"# hello"


def test_fetch_artifact_content_404(monkeypatch):
    class Response:
        status_code = 404
        content = b""

    monkeypatch.setattr(render.httpx, "get", lambda *a, **k: Response())
    status, content = render.fetch_artifact_content("art-1")
    assert status == 404
    assert content is None


def test_fetch_artifact_content_503(monkeypatch):
    class Response:
        status_code = 503
        content = b""

    monkeypatch.setattr(render.httpx, "get", lambda *a, **k: Response())
    status, content = render.fetch_artifact_content("art-1")
    assert status == 503
    assert content is None


def test_fetch_artifact_content_transport_error(monkeypatch):
    monkeypatch.setattr(
        render.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(render.httpx.HTTPError("boom"))
    )
    status, content = render.fetch_artifact_content("art-1")
    assert status == 0
    assert content is None


def test_render_artifact_buttons_fast_path_active(fake_streamlit, monkeypatch):
    artifact = {"artifact_id": "a1", "format": "md", "filename": "notes.md", "s3_key": "k"}
    monkeypatch.setattr(render, "fetch_artifact_content", lambda _id: (200, b"# notes"))
    render.render_artifact_buttons([artifact])
    assert len(fake_streamlit.download_button.calls) == 1
    call = fake_streamlit.download_button.calls[0]
    assert call["label"] == "Download MD"
    assert call["data"] == b"# notes"
    assert call["file_name"] == "notes.md"
    assert call["mime"] == "text/markdown"
    assert call["disabled"] is False


def test_render_artifact_buttons_404_warns(fake_streamlit, monkeypatch):
    artifact = {"artifact_id": "a1", "format": "md", "filename": "notes.md"}
    monkeypatch.setattr(render, "fetch_artifact_content", lambda _id: (404, None))
    render.render_artifact_buttons([artifact])
    assert fake_streamlit.warnings == ["Artifact not found (notes.md)"]
    assert fake_streamlit.download_button.calls == []


def test_render_artifact_buttons_slow_path_generating(fake_streamlit, monkeypatch):
    artifact = {"artifact_id": "a1", "format": "pdf", "filename": "report.pdf"}
    monkeypatch.setattr(render, "fetch_artifact_content", lambda _id: (503, None))
    render.render_artifact_buttons([artifact])
    assert fake_streamlit.warnings == ["Still generating"]
    assert len(fake_streamlit.download_button.calls) == 1
    call = fake_streamlit.download_button.calls[0]
    assert call["disabled"] is True
    assert call["label"] == "Download PDF (Generating...)"
    assert call["mime"] == "application/pdf"


def test_render_artifact_buttons_multiple(fake_streamlit, monkeypatch):
    artifacts = [
        {"artifact_id": "a1", "format": "md", "filename": "one.md"},
        {"artifact_id": "a2", "format": "pdf", "filename": "two.pdf"},
        {"artifact_id": "a3", "format": "txt", "filename": "three.txt"},
    ]

    def fake_fetch(artifact_id):
        if artifact_id == "a2":
            return 503, None
        return 200, b"content"

    monkeypatch.setattr(render, "fetch_artifact_content", fake_fetch)
    render.render_artifact_buttons(artifacts)
    assert len(fake_streamlit.download_button.calls) == 3
    active = [c for c in fake_streamlit.download_button.calls if not c["disabled"]]
    assert len(active) == 2


def test_render_artifact_buttons_skips_missing_artifact_id(fake_streamlit, monkeypatch):
    monkeypatch.setattr(render, "fetch_artifact_content", lambda _id: (200, b""))
    render.render_artifact_buttons([{"format": "md", "filename": "x.md"}])
    assert fake_streamlit.download_button.calls == []


def test_render_artifact_buttons_retry_reruns(fake_streamlit, monkeypatch):
    artifact = {"artifact_id": "a1", "format": "pdf", "filename": "report.pdf"}
    monkeypatch.setattr(render, "fetch_artifact_content", lambda _id: (503, None))
    fake_streamlit._button_clicked = True
    with pytest.raises(_FakeRerun):
        render.render_artifact_buttons([artifact])
    assert fake_streamlit.buttons == ["Retry report.pdf"]


def test_render_status_badge_streaming_uses_status(fake_streamlit):
    render.render_status_badge("streaming")
    assert fake_streamlit.status_calls == [
        {"label": "Generating response...", "expanded": False}
    ]
    assert fake_streamlit.errors == []
    assert fake_streamlit.warnings == []


def test_render_status_badge_cancelled_with_detail(fake_streamlit):
    render.render_status_badge("cancelled", "user_cancelled")
    assert fake_streamlit.errors == ["Cancelled: user_cancelled"]
    assert fake_streamlit.warnings == []


def test_render_status_badge_cancelled_without_detail(fake_streamlit):
    render.render_status_badge("cancelled")
    assert fake_streamlit.errors == ["Cancelled"]


def test_render_status_badge_error_with_traceback(fake_streamlit):
    render.render_status_badge("error", "LLM provider failed", "traceback\nline")
    assert fake_streamlit.warnings == ["Error: LLM provider failed"]
    assert fake_streamlit.expander_calls == [{"label": "Details", "expanded": False}]
    assert fake_streamlit.code_calls == [
        {"text": "traceback\nline", "language": "python"}
    ]


def test_render_status_badge_error_without_traceback(fake_streamlit):
    render.render_status_badge("error", "boom")
    assert fake_streamlit.warnings == ["Error: boom"]
    assert fake_streamlit.expander_calls == []


def test_render_status_badge_error_without_detail(fake_streamlit):
    render.render_status_badge("error")
    assert fake_streamlit.warnings == ["Error"]


def test_render_status_badge_unknown_status_warns(fake_streamlit):
    render.render_status_badge("nope")
    assert fake_streamlit.warnings == ["Unknown status: nope"]


def test_pii_level_low():
    assert render.pii_level(0.0, 0.3, 0.7) == "low"
    assert render.pii_level(0.29, 0.3, 0.7) == "low"


def test_pii_level_medium():
    assert render.pii_level(0.3, 0.3, 0.7) == "medium"
    assert render.pii_level(0.5, 0.3, 0.7) == "medium"


def test_pii_level_high():
    assert render.pii_level(0.7, 0.3, 0.7) == "high"
    assert render.pii_level(1.0, 0.3, 0.7) == "high"


def test_pii_thresholds_defaults():
    assert render.pii_thresholds() == (0.3, 0.7)


def test_pii_thresholds_from_env(monkeypatch):
    monkeypatch.setenv(render.PII_LOW_THRESHOLD_ENV, "0.1")
    monkeypatch.setenv(render.PII_HIGH_THRESHOLD_ENV, "0.8")
    assert render.pii_thresholds() == (0.1, 0.8)


def test_entity_types_for_badge_dicts():
    entities = [{"type": "PERSON"}, {"type": "US_SSN"}, {}]
    assert render.entity_types_for_badge(entities) == ["PERSON", "US_SSN"]


def test_entity_types_for_badge_strings():
    assert render.entity_types_for_badge(["PERSON", "URL"]) == ["PERSON", "URL"]


def test_entity_types_for_badge_empty_and_none():
    assert render.entity_types_for_badge(None) == []
    assert render.entity_types_for_badge([]) == []


def test_render_pii_badge_low_is_green(fake_streamlit):
    render.render_pii_badge(0.1, ["URL"])
    assert len(fake_streamlit.markdown_calls) == 1
    html_text = fake_streamlit.markdown_calls[0]["text"]
    assert "PII: low" in html_text
    assert "#2f9e44" in html_text


def test_render_pii_badge_medium_is_amber(fake_streamlit):
    render.render_pii_badge(0.5, [])
    html_text = fake_streamlit.markdown_calls[0]["text"]
    assert "PII: medium" in html_text
    assert "#f59f00" in html_text


def test_render_pii_badge_high_is_red_with_tooltip(fake_streamlit):
    render.render_pii_badge(0.9, ["PERSON", "US_SSN"])
    html_text = fake_streamlit.markdown_calls[0]["text"]
    assert "PII: high" in html_text
    assert "#e03131" in html_text
    assert "Detected entities: PERSON, US_SSN" in html_text


def test_render_pii_badge_uses_unsafe_html(fake_streamlit):
    render.render_pii_badge(0.7)
    assert fake_streamlit.markdown_calls[0]["unsafe_allow_html"] is True


def test_render_pii_badge_custom_thresholds(fake_streamlit):
    render.render_pii_badge(0.5, low_threshold=0.3, high_threshold=0.9)
    assert "PII: medium" in fake_streamlit.markdown_calls[0]["text"]


def test_render_message_renders_pii_badge_for_user(fake_streamlit):
    render.render_message(
        "user",
        "My name is John Smith",
        {"message_id": "m1", "pii_score": 0.92, "pii_entities": [{"type": "PERSON"}]},
    )
    assert fake_streamlit.chat_messages == ["user"]
    assert fake_streamlit.markdown_calls[0]["text"] == "My name is John Smith"
    assert "PII: high" in fake_streamlit.markdown_calls[1]["text"]


def test_render_message_without_metadata_no_badge(fake_streamlit):
    render.render_message("user", "hello")
    assert fake_streamlit.chat_messages == ["user"]
    assert len(fake_streamlit.markdown_calls) == 1


def test_render_message_user_metadata_without_pii_score_no_badge(fake_streamlit):
    render.render_message("user", "hello", {"some_key": 1})
    assert len(fake_streamlit.markdown_calls) == 1


def test_render_message_assistant_never_renders_badge(fake_streamlit):
    render.render_message(
        "assistant",
        "answered",
        {"message_id": "m1", "pii_score": 0.95, "pii_entities": ["US_SSN"]},
    )
    assert fake_streamlit.chat_messages == ["assistant"]
    assert len(fake_streamlit.markdown_calls) == 1
    assert "PII" not in fake_streamlit.markdown_calls[0]["text"]


def test_render_history_passes_metadata(fake_streamlit):
    messages = [
        {"role": "user", "content": "hi", "metadata": {"pii_score": 0.1, "pii_entities": []}},
        {"role": "assistant", "content": "hello", "metadata": None},
        {"role": "user", "content": "boost", "metadata": {"pii_score": 0.8}},
    ]
    render.render_history(messages)
    assert fake_streamlit.chat_messages == ["user", "assistant", "user"]
    assert fake_streamlit.markdown_calls[0]["text"] == "hi"
    assert "PII: low" in fake_streamlit.markdown_calls[1]["text"]
    assert fake_streamlit.markdown_calls[2]["text"] == "hello"
    assert fake_streamlit.markdown_calls[3]["text"] == "boost"
    assert "PII: high" in fake_streamlit.markdown_calls[4]["text"]


# G-1 Tool-call preview tests
def test_render_tool_call_running(fake_streamlit):
    render._render_tool_call_fragment("web_search", {"query": "python", "max_results": 5}, "running")
    assert fake_streamlit.expander_calls == [{"label": "🔧 web_search — running", "expanded": False}]
    assert len(fake_streamlit.json_calls) == 1
    assert fake_streamlit.json_calls[0] == {"query": "python", "max_results": 5}
    assert len(fake_streamlit.spinner_calls) == 1
    assert fake_streamlit.spinner_text == "Running..."


def test_render_tool_call_done_with_preview(fake_streamlit):
    preview = {"snippet_count": 3, "sources": ["example.com"]}
    render._render_tool_call_fragment("web_search", {"query": "python"}, "done", preview)
    assert fake_streamlit.expander_calls == [{"label": "🔧 web_search — done", "expanded": False}]
    assert len(fake_streamlit.json_calls) == 2
    assert fake_streamlit.json_calls[0] == {"query": "python"}
    assert fake_streamlit.json_calls[1] == {"snippet_count": 3, "sources": ["example.com"]}
    assert fake_streamlit.success_calls == "Done"


def test_render_tool_call_error(fake_streamlit):
    render._render_tool_call_fragment("rag_query", {"query": "error"}, "error")
    assert fake_streamlit.expander_calls == [{"label": "🔧 rag_query — error", "expanded": False}]
    assert len(fake_streamlit.json_calls) == 1
    assert fake_streamlit.json_calls[0] == {"query": "error"}
    assert len(fake_streamlit.errors) == 1
    assert fake_streamlit.errors[0] == "Failed"


def test_render_tool_call_file_export_content_truncation(fake_streamlit):
    long_content = "x" * 300
    render._render_tool_call_fragment("file_export", {"content": long_content, "filename": "test.txt"})
    assert fake_streamlit.json_calls[0] == {"content": "x" * 200 + "...", "filename": "test.txt"}


def test_handle_tool_event_tool_call(fake_streamlit):
    client = fake_streamlit  # Mock client
    pending_tool_calls = {}
    
    data = {
        "tool_call_id": "tc1",
        "tool_name": "web_search",
        "args": {"query": "python", "max_results": 5}
    }
    
    render.handle_tool_event("tool_call", data, client, pending_tool_calls)
    assert len(pending_tool_calls) == 1
    assert pending_tool_calls["tc1"]["tool_name"] == "web_search"
    assert pending_tool_calls["tc1"]["status"] == "running"
    assert client.tool_call_rendered["tool_name"] == "web_search"
    assert client.tool_call_rendered["status"] == "running"


def test_handle_tool_event_tool_result(fake_streamlit):
    client = fake_streamlit  # Mock client
    pending_tool_calls = {
        "tc1": {
            "tool_name": "web_search",
            "args": {"query": "python"},
            "status": "running",
            "result_preview": None
        }
    }
    
    data = {
        "tool_call_id": "tc1",
        "preview": {"snippet_count": 3}
    }
    
    render.handle_tool_event("tool_result", data, client, pending_tool_calls)
    assert pending_tool_calls["tc1"]["status"] == "done"
    assert pending_tool_calls["tc1"]["result_preview"] == {"snippet_count": 3}
    assert client.tool_call_rendered["status"] == "done"
    assert client.tool_call_rendered["result_preview"] == {"snippet_count": 3}


def test_handle_tool_event_retrieved_docs(fake_streamlit):
    client = fake_streamlit  # Mock client
    pending_tool_calls = {
        "tc1": {
            "tool_name": "rag_query",
            "args": {"query": "error"},
            "status": "running",
            "result_preview": None
        }
    }

    data = {
        "tool_call_id": "tc1",
        "chunk_count": 5,
        "top_score": 0.95,
        "source_uris": ["doc1.pdf", "doc2.txt"],
        "chunks": [
            {"source_uri": "doc1.pdf", "content_preview": "Error 123", "score": 0.95}
        ]
    }

    render.handle_tool_event("retrieved_docs", data, client, pending_tool_calls)
    assert pending_tool_calls["tc1"]["status"] == "done"
    assert pending_tool_calls["tc1"]["result_preview"]["chunk_count"] == 5
    assert pending_tool_calls["tc1"]["result_preview"]["top_score"] == 0.95
    assert client.tool_call_rendered["status"] == "done"
    assert len(fake_streamlit.expander_calls) == 1  # Only citations panel gets added, tool call updates existing


def test_render_rag_citations_empty(fake_streamlit):
    render.render_rag_citations([])
    assert fake_streamlit.expander_calls == []
    assert fake_streamlit.markdown_calls == []


def test_render_rag_citations_one_chunk(fake_streamlit):
    chunks = [
        {
            "source_uri": "s3://docs/manual.pdf",
            "title": "Manual",
            "page": 7,
            "content_preview": "Error 123",
            "score": 0.95,
        }
    ]
    render.render_rag_citations(chunks)
    assert fake_streamlit.expander_calls == [
        {"label": "📚 RAG citations (1 chunks)", "expanded": False}
    ]
    assert fake_streamlit.markdown_calls[0]["text"] == (
        "**1. [Manual](s3://docs/manual.pdf)**"
    )
    assert fake_streamlit.caption_calls == ["📎 s3://docs/manual.pdf · 📄 p.7"]
    assert fake_streamlit.progress_calls == [{"value": 0.95, "text": "Relevance: 0.95"}]
    assert fake_streamlit.markdown_calls[1]["text"] == "Error 123"
    assert len(fake_streamlit.divider_calls) == 1


def test_render_rag_citations_many_chunks(fake_streamlit):
    chunks = [
        {
            "source_uri": f"s3://docs/doc{i}.pdf",
            "title": f"Doc {i}",
            "page": i,
            "content_preview": f"content {i}",
            "score": 0.9 - i / 10,
        }
        for i in range(1, 6)
    ]
    render.render_rag_citations(chunks)
    assert fake_streamlit.expander_calls == [
        {"label": "📚 RAG citations (5 chunks)", "expanded": False}
    ]
    assert len(fake_streamlit.divider_calls) == 5
    assert len(fake_streamlit.progress_calls) == 5
    assert fake_streamlit.markdown_calls[0]["text"] == "**1. [Doc 1](s3://docs/doc1.pdf)**"
    assert fake_streamlit.markdown_calls[8]["text"] == "**5. [Doc 5](s3://docs/doc5.pdf)**"


def test_render_rag_citations_count_follows_chunks(fake_streamlit):
    chunks = [{"source_uri": "a", "score": 0.1}] * 3
    render.render_rag_citations(chunks)
    assert fake_streamlit.expander_calls == [
        {"label": "📚 RAG citations (3 chunks)", "expanded": False}
    ]
    assert len(fake_streamlit.markdown_calls) == 6


def test_render_rag_citations_long_content(fake_streamlit):
    long_content = "x" * 500
    render.render_rag_citations(
        [{"source_uri": "s3://docs/big.pdf", "content_preview": long_content, "score": 0.5}]
    )
    assert fake_streamlit.markdown_calls[1]["text"] == "x" * 200 + "..."
    assert len(fake_streamlit.markdown_calls[1]["text"]) == 203


def test_render_rag_citations_short_content_not_truncated(fake_streamlit):
    render.render_rag_citations(
        [{"source_uri": "s3://docs/a.pdf", "content_preview": "short", "score": 0.5}]
    )
    assert fake_streamlit.markdown_calls[1]["text"] == "short"


def test_render_rag_citations_missing_fields(fake_streamlit):
    render.render_rag_citations([{"content_preview": "body"}])
    assert fake_streamlit.markdown_calls[0]["text"] == "**1. Chunk 1**"
    assert fake_streamlit.caption_calls == ["📎 unknown source"]
    assert fake_streamlit.progress_calls == [{"value": 0.0, "text": "Relevance: 0.00"}]


def test_render_rag_citations_title_falls_back_to_source_uri(fake_streamlit):
    render.render_rag_citations(
        [{"source_uri": "s3://docs/a.pdf", "content_preview": "body", "score": 0.4}]
    )
    assert fake_streamlit.markdown_calls[0]["text"] == "**1. [s3://docs/a.pdf](s3://docs/a.pdf)**"
    assert fake_streamlit.caption_calls == ["📎 s3://docs/a.pdf"]


def test_render_rag_citations_escapes_brackets_in_title(fake_streamlit):
    render.render_rag_citations(
        [{"source_uri": "s3://a.pdf", "title": "Chapter [1]", "content_preview": "x", "score": 0.2}]
    )
    assert fake_streamlit.markdown_calls[0]["text"] == "**1. [Chapter \\[1\\]](s3://a.pdf)**"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0.95, 0.95), (None, 0.0), ("n/a", 0.0), (-1.0, 0.0), (4.2, 1.0)],
)
def test_render_rag_citations_score_normalized(fake_streamlit, raw, expected):
    render.render_rag_citations([{"source_uri": "s3://a.pdf", "content_preview": "x", "score": raw}])
    assert fake_streamlit.progress_calls[0]["value"] == expected


def test_render_rag_citations_fragment_isolates_reruns(fake_streamlit, monkeypatch):
    render._render_rag_citations_fragment([{"source_uri": "s3://a.pdf", "score": 0.3}])
    assert fake_streamlit.fragments == ["_fragment"]
    assert fake_streamlit.expander_calls == [
        {"label": "📚 RAG citations (1 chunks)", "expanded": False}
    ]


def test_handle_tool_event_retrieved_docs_renders_citations(fake_streamlit, monkeypatch):
    client = fake_streamlit
    pending_tool_calls = {
        "tc1": {
            "tool_name": "rag_query",
            "args": {"query": "error"},
            "status": "running",
            "result_preview": None,
        }
    }
    chunks = [
        {"source_uri": "s3://doc1.pdf", "title": "Doc 1", "content_preview": "Error 123", "score": 0.95}
    ]
    data = {
        "tool_call_id": "tc1",
        "chunk_count": 5,
        "top_score": 0.95,
        "source_uris": ["s3://doc1.pdf"],
        "chunks": chunks,
    }

    captured = []
    monkeypatch.setattr(
        render, "_render_rag_citations_fragment", lambda c: captured.append(c)
    )

    render.handle_tool_event("retrieved_docs", data, client, pending_tool_calls)

    assert captured == [chunks]
    assert client.tool_call_rendered["result_preview"]["chunk_count"] == 5
    assert client.tool_call_rendered["result_preview"]["source_uris"] == ["s3://doc1.pdf"]


# G-3 Web search results panel tests
WEB_PANEL = "\U0001f310 Web search results"


def test_render_web_search_results_empty(fake_streamlit):
    render.render_web_search_results([])
    assert fake_streamlit.expander_calls == []
    assert fake_streamlit.markdown_calls == []
    assert fake_streamlit.metric_calls == []


def test_render_web_search_results_one(fake_streamlit):
    results = [
        {
            "title": "Python asyncio docs",
            "url": "https://docs.python.org/3/library/asyncio.html",
            "snippet": "asyncio is a library for asynchronous Python.",
            "score": 0.95,
        }
    ]
    render.render_web_search_results(results)

    assert fake_streamlit.expander_calls == [{"label": f"{WEB_PANEL} (1)", "expanded": False}]
    assert fake_streamlit.markdown_calls[0]["text"] == (
        "**1. [Python asyncio docs](https://docs.python.org/3/library/asyncio.html)**"
    )
    assert fake_streamlit.caption_calls == [
        "\U0001f517 https://docs.python.org/3/library/asyncio.html"
    ]
    assert fake_streamlit.markdown_calls[1]["text"] == (
        "asyncio is a library for asynchronous Python."
    )
    assert fake_streamlit.metric_calls == [{"label": "Relevance", "value": "0.95"}]
    assert len(fake_streamlit.divider_calls) == 1


def test_render_web_search_results_many(fake_streamlit):
    results = [
        {
            "title": f"Result {i}",
            "url": f"https://example.com/{i}",
            "snippet": f"snippet {i}",
            "score": 0.9,
        }
        for i in range(1, 6)
    ]
    render.render_web_search_results(results)

    assert fake_streamlit.expander_calls == [{"label": f"{WEB_PANEL} (5)", "expanded": False}]
    assert len(fake_streamlit.divider_calls) == 5
    assert len(fake_streamlit.metric_calls) == 5
    assert fake_streamlit.markdown_calls[0]["text"] == (
        "**1. [Result 1](https://example.com/1)**"
    )
    assert fake_streamlit.markdown_calls[8]["text"] == (
        "**5. [Result 5](https://example.com/5)**"
    )


def test_render_web_search_results_count_is_not_hardcoded(fake_streamlit):
    render.render_web_search_results([{"title": "a", "url": "https://a", "snippet": "s"}] * 17)
    assert fake_streamlit.expander_calls == [{"label": f"{WEB_PANEL} (17)", "expanded": False}]


def test_render_web_search_results_missing_snippet(fake_streamlit):
    render.render_web_search_results(
        [{"title": "No snippet", "url": "https://example.com", "score": 0.5}]
    )
    assert fake_streamlit.markdown_calls[0]["text"] == (
        "**1. [No snippet](https://example.com)**"
    )
    assert len(fake_streamlit.markdown_calls) == 1
    assert len(fake_streamlit.divider_calls) == 1


def test_render_web_search_results_missing_score(fake_streamlit):
    render.render_web_search_results(
        [{"title": "No score", "url": "https://example.com", "snippet": "body"}]
    )
    assert fake_streamlit.metric_calls == []


def test_render_web_search_results_invalid_score_is_skipped(fake_streamlit):
    render.render_web_search_results(
        [{"title": "Bad score", "url": "https://example.com", "score": "n/a"}]
    )
    assert fake_streamlit.metric_calls == []
    assert len(fake_streamlit.divider_calls) == 1


def test_render_web_search_results_missing_fields(fake_streamlit):
    render.render_web_search_results([{}])
    assert fake_streamlit.markdown_calls[0]["text"] == "**1. Result 1**"
    assert fake_streamlit.caption_calls == ["\U0001f517 "]
    assert fake_streamlit.metric_calls == []


def test_render_web_search_results_title_falls_back_to_url(fake_streamlit):
    render.render_web_search_results([{"url": "https://example.com", "snippet": "x"}])
    assert fake_streamlit.markdown_calls[0]["text"] == (
        "**1. [https://example.com](https://example.com)**"
    )


def test_render_web_search_results_escapes_brackets_in_title(fake_streamlit):
    render.render_web_search_results(
        [{"title": "Chapter [1]", "url": "https://example.com", "snippet": "x"}]
    )
    assert fake_streamlit.markdown_calls[0]["text"] == (
        "**1. [Chapter \\[1\\]](https://example.com)**"
    )


def test_render_web_search_results_hides_technical_fields(fake_streamlit):
    render.render_web_search_results(
        [
            {
                "title": "T",
                "url": "https://example.com",
                "snippet": "**bold** snippet",
                "raw_tavily_field": "must not render",
            }
        ]
    )
    texts = [call["text"] for call in fake_streamlit.markdown_calls]
    assert texts == ["**1. [T](https://example.com)**", "**bold** snippet"]
    assert not any("must not render" in text for text in texts)


def test_render_web_search_results_uses_separate_expander_from_rag(fake_streamlit):
    render.render_rag_citations(
        [{"source_uri": "s3://doc.pdf", "content_preview": "x", "score": 0.5}]
    )
    render.render_web_search_results([{"title": "T", "url": "https://example.com", "snippet": "x"}])
    assert [call["label"] for call in fake_streamlit.expander_calls] == [
        "\U0001f4da RAG citations (1 chunks)",
        f"{WEB_PANEL} (1)",
    ]


def test_render_web_search_results_fragment_isolates_reruns(fake_streamlit):
    render._render_web_search_results_fragment(
        [{"title": "T", "url": "https://example.com", "snippet": "x"}]
    )
    assert fake_streamlit.fragments == ["_fragment"]
    assert fake_streamlit.expander_calls == [{"label": f"{WEB_PANEL} (1)", "expanded": False}]


def test_handle_tool_event_web_search_full_results(fake_streamlit, monkeypatch):
    client = fake_streamlit
    pending_tool_calls = {
        "tc1": {
            "tool_name": "web_search",
            "args": {"query": "python asyncio"},
            "status": "running",
            "result_preview": None,
        }
    }
    full_results = [{"title": "T", "url": "https://example.com", "snippet": "x", "score": 0.9}]
    data = {
        "tool_call_id": "tc1",
        "tool_name": "web_search",
        "preview": {"snippet_count": 1},
        "full_results": full_results,
    }

    captured = []
    monkeypatch.setattr(
        render,
        "_render_web_search_results_fragment",
        lambda r: captured.append(r),
    )

    render.handle_tool_event("tool_result", data, client, pending_tool_calls)

    assert captured == [full_results]
    assert client.tool_call_rendered["result_preview"] == {"snippet_count": 1}
    assert pending_tool_calls["tc1"]["status"] == "done"


def test_handle_tool_event_web_search_renders_results_panel(fake_streamlit):
    client = fake_streamlit
    pending_tool_calls = {
        "tc1": {
            "tool_name": "web_search",
            "args": {"query": "python asyncio"},
            "status": "running",
            "result_preview": None,
        }
    }
    data = {
        "tool_call_id": "tc1",
        "tool_name": "web_search",
        "preview": {"snippet_count": 1},
        "full_results": [
            {
                "title": "Python asyncio docs",
                "url": "https://docs.python.org/3/library/asyncio.html",
                "snippet": "asyncio is a library for asynchronous Python.",
                "score": 0.95,
            }
        ],
    }

    render.handle_tool_event("tool_result", data, client, pending_tool_calls)

    assert fake_streamlit.expander_calls == [{"label": f"{WEB_PANEL} (1)", "expanded": False}]
    assert fake_streamlit.markdown_calls[0]["text"] == (
        "**1. [Python asyncio docs](https://docs.python.org/3/library/asyncio.html)**"
    )
    assert fake_streamlit.metric_calls == [{"label": "Relevance", "value": "0.95"}]


def test_handle_tool_event_web_search_without_results_renders_nothing(fake_streamlit):
    client = fake_streamlit
    pending_tool_calls = {
        "tc1": {
            "tool_name": "web_search",
            "args": {"query": "python"},
            "status": "running",
            "result_preview": None,
        }
    }
    data = {"tool_call_id": "tc1", "preview": {"snippet_count": 0}}

    render.handle_tool_event("tool_result", data, client, pending_tool_calls)

    assert fake_streamlit.expander_calls == []
    assert pending_tool_calls["tc1"]["status"] == "done"


def test_handle_tool_event_non_web_search_does_not_render_web_panel(fake_streamlit):
    client = fake_streamlit
    pending_tool_calls = {
        "tc1": {
            "tool_name": "file_export",
            "args": {"filename": "a.txt"},
            "status": "running",
            "result_preview": None,
        }
    }
    data = {
        "tool_call_id": "tc1",
        "tool_name": "file_export",
        "preview": {"filename": "a.txt"},
        "full_results": [{"title": "T", "url": "https://example.com"}],
    }

    render.handle_tool_event("tool_result", data, client, pending_tool_calls)

    assert fake_streamlit.expander_calls == []


# ── Settings Panel Tests (G-4) ─────────────────────────────────────────────────────


def test_render_settings_panel_defaults():
    """Test render_settings_panel with default values (all tools enabled)."""
    session_state = {}
    settings = render.render_settings_panel(session_state)
    
    # Check default values
    assert settings["tools_enabled"] == ["web_search", "rag_query", "file_export"]
    assert settings["retrieval_strategy"] == "hybrid"
    assert settings["reranker"] == "bge"
    assert settings["max_results"] == 5
    assert settings["top_k"] == 5
    
    # Check session_state persistence
    assert session_state["settings"] == settings


def test_render_settings_panel_disable_web_search():
    """Test render_settings_panel with web_search disabled."""
    session_state = {}
    
    # Mock st.checkbox to return False for web_search
    import streamlit as st
    original_checkbox = st.checkbox
    
    def mock_checkbox(label, value=True, key=None):
        if key == "settings_tool_web_search":
            return False  # Disable web_search
        return original_checkbox(label, value, key)
    
    st.checkbox = mock_checkbox
    
    try:
        settings = render.render_settings_panel(session_state)
        
        # Check web_search is disabled
        assert "web_search" not in settings["tools_enabled"]
        assert settings["tools_enabled"] == ["rag_query", "file_export"]
        assert settings["max_results"] == 5  # Default even when disabled
    finally:
        st.checkbox = original_checkbox


def test_render_settings_panel_disable_rag_query():
    """Test render_settings_panel with rag_query disabled (retrieval section hidden)."""
    session_state = {}
    
    # Mock st.checkbox to return False for rag_query
    import streamlit as st
    original_checkbox = st.checkbox
    
    def mock_checkbox(label, value=True, key=None):
        if key == "settings_tool_rag_query":
            return False  # Disable rag_query
        return original_checkbox(label, value, key)
    
    st.checkbox = mock_checkbox
    
    try:
        settings = render.render_settings_panel(session_state)
        
        # Check rag_query is disabled
        assert "rag_query" not in settings["tools_enabled"]
        assert settings["tools_enabled"] == ["web_search", "file_export"]
        
        # Check defaults when rag_query is disabled
        assert settings["retrieval_strategy"] == "hybrid"
        assert settings["reranker"] == "bge"
        assert settings["top_k"] == 5
    finally:
        st.checkbox = original_checkbox


def test_render_settings_panel_choose_vector():
    """Test render_settings_panel with vector retrieval strategy."""
    session_state = {}
    
    # Mock st.selectbox to return "vector"
    import streamlit as st
    original_selectbox = st.selectbox
    
    def mock_selectbox(label, options=None, index=0, key=None, help=None):
        if key == "settings_retrieval_strategy":
            return "vector"  # Choose vector strategy
        return original_selectbox(label, options, index, key, help)
    
    st.selectbox = mock_selectbox
    
    try:
        settings = render.render_settings_panel(session_state)
        
        # Check vector strategy is selected
        assert settings["retrieval_strategy"] == "vector"
        assert settings["top_k"] == 5  # Default slider value
    finally:
        st.selectbox = original_selectbox


def test_render_settings_panel_choose_cohere():
    """Test render_settings_panel with Cohere reranker."""
    session_state = {}
    
    # Mock st.radio to return "cohere"
    import streamlit as st
    original_radio = st.radio
    
    def mock_radio(label, options=None, index=0, key=None, help=None):
        if key == "settings_reranker":
            return "cohere"  # Choose Cohere reranker
        return original_radio(label, options, index, key, help)
    
    st.radio = mock_radio
    
    try:
        settings = render.render_settings_panel(session_state)
        
        # Check Cohere reranker is selected
        assert settings["reranker"] == "cohere"
        assert settings["top_k"] == 5  # Default slider value
    finally:
        st.radio = original_radio


def test_render_settings_panel_choose_none_reranker():
    """Test render_settings_panel with no reranker (A/B baseline mode)."""
    session_state = {}
    
    # Mock st.radio to return "none"
    import streamlit as st
    original_radio = st.radio
    
    def mock_radio(label, options=None, index=0, key=None, help=None):
        if key == "settings_reranker":
            return "none"  # Disable reranker (A/B baseline)
        return original_radio(label, options, index, key, help)
    
    st.radio = mock_radio
    
    try:
        settings = render.render_settings_panel(session_state)
        
        # Check no reranker is selected
        assert settings["reranker"] == "none"
        assert settings["top_k"] == 5  # Default slider value
    finally:
        st.radio = original_radio


# ── G-1..G-3: result payloads are recorded so panels survive a fragment rerun ──
def test_handle_tool_event_tool_result_records_full_results(fake_streamlit):
    pending_tool_calls = {
        "tc1": {
            "tool_name": "web_search",
            "args": {"query": "python"},
            "status": "running",
            "result_preview": None,
        }
    }
    data = {
        "tool_call_id": "tc1",
        "preview": {"snippet_count": 2},
        "full_results": [
            {"title": "asyncio", "url": "https://docs.python.org", "snippet": "..."}
        ],
    }

    render.handle_tool_event("tool_result", data, fake_streamlit, pending_tool_calls)
    assert pending_tool_calls["tc1"]["full_results"] == data["full_results"]


def test_handle_tool_event_tool_result_without_full_results_omits_key(fake_streamlit):
    pending_tool_calls = {
        "tc1": {
            "tool_name": "file_export",
            "args": {},
            "status": "running",
            "result_preview": None,
        }
    }
    data = {"tool_call_id": "tc1", "preview": {"artifact_id": "a1"}}

    render.handle_tool_event("tool_result", data, fake_streamlit, pending_tool_calls)
    assert "full_results" not in pending_tool_calls["tc1"]


def test_handle_tool_event_retrieved_docs_records_chunks(fake_streamlit):
    pending_tool_calls = {
        "tc1": {
            "tool_name": "rag_query",
            "args": {"query": "error"},
            "status": "running",
            "result_preview": None,
        }
    }
    chunks = [{"source_uri": "s3://docs/a.pdf", "score": 0.9}]
    data = {
        "tool_call_id": "tc1",
        "chunk_count": 1,
        "top_score": 0.9,
        "source_uris": ["s3://docs/a.pdf"],
        "chunks": chunks,
    }

    render.handle_tool_event("retrieved_docs", data, fake_streamlit, pending_tool_calls)
    assert pending_tool_calls["tc1"]["chunks"] == chunks


def test_render_tool_calls_empty_renders_nothing(fake_streamlit):
    render.render_tool_calls({})
    assert fake_streamlit.expander_calls == []


def test_render_tool_calls_rebuilds_preview_and_panels(fake_streamlit):
    pending_tool_calls = {
        "tc1": {
            "tool_name": "rag_query",
            "args": {"query": "error"},
            "status": "done",
            "result_preview": {"chunk_count": 1, "top_score": 0.9},
            "chunks": [{"source_uri": "s3://docs/a.pdf", "score": 0.9}],
        },
        "tc2": {
            "tool_name": "web_search",
            "args": {"query": "python"},
            "status": "done",
            "result_preview": {"snippet_count": 1},
            "full_results": [
                {"title": "asyncio", "url": "https://docs.python.org", "snippet": "..."}
            ],
        },
    }

    render.render_tool_calls(pending_tool_calls)

    labels = [call["label"] for call in fake_streamlit.expander_calls]
    assert labels == [
        "🔧 rag_query — done",
        "📚 RAG citations (1 chunks)",
        "🔧 web_search — done",
        "\U0001f310 Web search results (1)",
    ]


def test_render_tool_calls_renders_running_preview_without_panels(fake_streamlit):
    pending_tool_calls = {
        "tc1": {
            "tool_name": "web_search",
            "args": {"query": "python"},
            "status": "running",
            "result_preview": None,
        }
    }

    render.render_tool_calls(pending_tool_calls)

    assert fake_streamlit.expander_calls == [
        {"label": "🔧 web_search — running", "expanded": False}
    ]
    assert fake_streamlit.spinner_calls == ["Running..."]
