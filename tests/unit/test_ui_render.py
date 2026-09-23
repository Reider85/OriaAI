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
        self._button_clicked = False

    def warning(self, text):
        self.warnings.append(text)

    def error(self, text):
        self.errors.append(text)

    def status(self, label, expanded=None):
        self.status_calls.append({"label": label, "expanded": expanded})
        return _FakeStatus()

    def expander(self, label):
        self.expander_calls.append(label)
        return _FakeExpander()

    def code(self, text, language=None):
        self.code_calls.append({"text": text, "language": language})

    def button(self, label):
        self.buttons.append(label)
        return self._button_clicked

    def markdown(self, text, unsafe_allow_html=False):
        self.markdown_calls.append({"text": text, "unsafe_allow_html": unsafe_allow_html})

    def chat_message(self, role):
        self.chat_messages.append(role)
        return _FakeContainer()

    def rerun(self):
        raise _FakeRerun()


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
    assert fake_streamlit.expander_calls == ["Details"]
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
