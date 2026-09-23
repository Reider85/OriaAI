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
        self._button_clicked = False

    def warning(self, text):
        self.warnings.append(text)

    def button(self, label):
        self.buttons.append(label)
        return self._button_clicked

    def rerun(self):
        raise _FakeRerun()


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
