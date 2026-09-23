"""Unit tests for llm_client.ui.client UIClient ABC and types (UI-2, ADR-002)."""

import pytest
from pydantic import ValidationError

from llm_client.types import ArtifactRef
from llm_client.ui.client import UI_BACKEND_ENV, UIClient, get_ui_client


class TestUIClientABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError, match="abstract method"):
            UIClient()  # type: ignore[abstract]

    def test_complete_subclass_can_be_instantiated(self):
        class _DummyClient(UIClient):
            def render_message(self, role, content, metadata=None):
                pass

            def render_user_message(self, content):
                return None

            def render_artifact(self, artifact):
                pass

            def stream_token(self, token):
                pass

            def handle_user_input(self):
                return None

        client = _DummyClient()
        assert client is not None

    def test_incomplete_subclass_raises_type_error(self):
        class _IncompleteClient(UIClient):
            def render_message(self, role, content, metadata=None):
                pass

            def stream_token(self, token):
                pass

            def handle_user_input(self):
                return None

        with pytest.raises(TypeError, match="abstract method"):
            _IncompleteClient()


class TestArtifactRef:
    def test_valid_artifact(self):
        ref = ArtifactRef(
            artifact_id="art-1",
            format="pdf",
            filename="report.pdf",
            s3_key="artifacts/report.pdf",
        )
        assert ref.artifact_id == "art-1"
        assert ref.format == "pdf"
        assert ref.filename == "report.pdf"

    def test_invalid_format_rejected(self):
        with pytest.raises(ValidationError):
            ArtifactRef(
                artifact_id="art-1",
                format="csv",  # type: ignore[arg-type]
                filename="data.csv",
            )

    def test_all_valid_formats_accepted(self):
        for fmt in ("md", "txt", "pdf", "docx", "odt", "xls", "xlsx"):
            ref = ArtifactRef(
                artifact_id="art-1", format=fmt, filename=f"file.{fmt}"
            )
            assert ref.format == fmt


class TestMessageRole:
    def test_valid_roles(self):
        for role in ("user", "assistant", "system"):
            # Literal is enforced at type-checker level; runtime validation
            # happens where MessageRole is used (e.g. StreamlitClient).
            assert role in ("user", "assistant", "system")


class TestGetUiClient:
    def test_default_returns_streamlit(self, monkeypatch):
        monkeypatch.delenv(UI_BACKEND_ENV, raising=False)
        client = get_ui_client()
        from llm_client.ui.streamlit_client import StreamlitClient

        assert isinstance(client, StreamlitClient)

    def test_streamlit_backend(self, monkeypatch):
        monkeypatch.setenv(UI_BACKEND_ENV, "streamlit")
        client = get_ui_client()
        from llm_client.ui.streamlit_client import StreamlitClient

        assert isinstance(client, StreamlitClient)

    def test_unknown_backend_raises(self, monkeypatch):
        monkeypatch.setenv(UI_BACKEND_ENV, "chainlit")
        with pytest.raises(NotImplementedError, match="not implemented in Phase 1"):
            get_ui_client()
