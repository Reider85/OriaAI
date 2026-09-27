"""Unit tests for BgeRerankerAdapter."""

from unittest.mock import patch

import pytest

from llm_client.rag.rerankers.base import RerankResult
from llm_client.rag.rerankers.bge import BgeRerankerAdapter


class MockCrossEncoder:
    """Mock CrossEncoder for testing."""

    def __init__(self, model_name_or_path=None, device="cpu", max_length=512):
        self.model_name_or_path = model_name_or_path
        self.device = device
        self.max_length = max_length

    def predict(self, pairs, batch_size=8):
        """Return deterministic scores: first pair always highest."""
        return [0.9, 0.1, 0.7, 0.3, 0.8][: len(pairs)]


@pytest.fixture
def bge_reranker():
    """BgeRerankerAdapter with pre-loaded mock model."""
    adapter = BgeRerankerAdapter()
    adapter._model = MockCrossEncoder()
    return adapter


@pytest.fixture
def sample_documents():
    """5 sample documents for testing."""
    return [
        {"id": "doc1", "content": "This is about error codes and debugging"},
        {"id": "doc2", "content": "Unrelated document about cooking recipes"},
        {"id": "doc3", "content": "Another document about error handling"},
        {"id": "doc4", "content": "Document about system architecture"},
        {"id": "doc5", "content": "Final document about error recovery"},
    ]


# ---------- rerank() ----------

@pytest.mark.asyncio
async def test_rerank_returns_correct_count(bge_reranker, sample_documents):
    results = await bge_reranker.rerank("query", sample_documents, top_k=3)
    assert len(results) == 3
    assert all(isinstance(r, RerankResult) for r in results)


@pytest.mark.asyncio
async def test_rerank_sorted_by_score(bge_reranker, sample_documents):
    results = await bge_reranker.rerank("query", sample_documents, top_k=5)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_rerank_preserves_original_indices(bge_reranker, sample_documents):
    """Mock scores: [0.9(idx0), 0.1(idx1), 0.7(idx2), 0.3(idx3), 0.8(idx4)].
    Sorted desc: 0.9(idx0), 0.8(idx4), 0.7(idx2)."""
    results = await bge_reranker.rerank("query", sample_documents, top_k=3)
    original_indices = [r.original_index for r in results]
    assert original_indices == [0, 4, 2]


@pytest.mark.asyncio
async def test_rerank_empty_documents(bge_reranker):
    results = await bge_reranker.rerank("query", [], top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_rerank_top_k_exceeds_documents(bge_reranker, sample_documents):
    results = await bge_reranker.rerank("query", sample_documents, top_k=10)
    assert len(results) == len(sample_documents)


@pytest.mark.asyncio
async def test_rerank_without_ids(bge_reranker):
    docs = [{"content": "Doc A"}, {"content": "Doc B"}]
    results = await bge_reranker.rerank("query", docs, top_k=2)
    assert results[0].doc_id == "0"
    assert results[1].doc_id == "1"


@pytest.mark.asyncio
async def test_rerank_custom_batch_size(bge_reranker, sample_documents):
    captured = {}

    def mock_predict(pairs, batch_size=8):
        captured["batch_size"] = batch_size
        return [0.5] * len(pairs)

    bge_reranker._model.predict = mock_predict
    await bge_reranker.rerank("query", sample_documents, batch_size=16)
    assert captured["batch_size"] == 16


@pytest.mark.asyncio
async def test_rerank_truncates_long_content():
    """max_length is applied to document content before predict."""
    captured_pairs = []

    class CaptureEncoder:
        def predict(self, pairs, batch_size=8):
            captured_pairs.extend(pairs)
            return [0.5] * len(pairs)

    adapter = BgeRerankerAdapter(max_length=10)
    adapter._model = CaptureEncoder()

    long_doc = [{"content": "x" * 100, "id": "long"}]
    await adapter.rerank("q", long_doc, top_k=1)

    assert len(captured_pairs[0][1]) == 10


# ---------- lazy loading ----------

@pytest.mark.asyncio
async def test_lazy_loading_not_loaded_in_init():
    adapter = BgeRerankerAdapter()
    assert adapter._model is None


@pytest.mark.asyncio
async def test_lazy_loading_loads_on_first_rerank():
    with patch("llm_client.rag.rerankers.bge.CrossEncoder") as mock_cls:
        mock_cls.return_value = MockCrossEncoder()
        adapter = BgeRerankerAdapter(model_dir="/fake/path")
        assert adapter._model is None

        await adapter.rerank("query", [{"content": "text"}])

        assert adapter._model is not None
        mock_cls.assert_called_once()


# ---------- health_check ----------

@pytest.mark.asyncio
async def test_health_check_success(bge_reranker):
    assert await bge_reranker.health_check() is True


@pytest.mark.asyncio
async def test_health_check_failure():
    with patch("llm_client.rag.rerankers.bge.CrossEncoder", side_effect=RuntimeError("fail")):
        adapter = BgeRerankerAdapter(model_dir="/fake/path")
        assert await adapter.health_check() is False


# ---------- name ----------

def test_name_property(bge_reranker):
    assert bge_reranker.name == "bge-reranker-base"


# ---------- constructor defaults ----------

@pytest.mark.asyncio
async def test_constructor_reads_env(monkeypatch):
    monkeypatch.setenv("RERANKER_DEVICE", "cuda")
    monkeypatch.setenv("RERANKER_MAX_LENGTH", "256")
    monkeypatch.setenv("RERANKER_BATCH_SIZE", "16")

    adapter = BgeRerankerAdapter()
    assert adapter._device == "cuda"
    assert adapter._max_length == 256
    assert adapter._batch_size == 16


@pytest.mark.asyncio
async def test_constructor_explicit_params():
    adapter = BgeRerankerAdapter(
        model_name="custom/model",
        model_dir="/custom/dir",
        device="cuda",
        max_length=256,
        batch_size=32,
    )
    assert adapter._model_name == "custom/model"
    assert adapter._model_dir == "/custom/dir"
    assert adapter._device == "cuda"
    assert adapter._max_length == 256
    assert adapter._batch_size == 32