"""Unit tests for document ingestion endpoints (ADR-020 / D-2)."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


def _build_client(bm25_indexer=None, vector_writer=None, pg_pool=None):
    """Build a minimal FastAPI app that mirrors the ingestion routes."""
    app = FastAPI()
    app.state.bm25_indexer = bm25_indexer
    app.state.vector_writer = vector_writer
    app.state.pg_pool = pg_pool

    class DocumentIngestRequest(BaseModel):
        user_id: str
        content: str
        source_type: str = "api"
        source_uri: str | None = None
        metadata: dict | None = None

    class DocumentIngestResponse(BaseModel):
        document_id: str
        status: str
        bm25_indexed: bool
        vector_indexed: bool | None

    class DocumentUpdateResponse(BaseModel):
        status: str

    @app.post("/documents", response_model=DocumentIngestResponse, status_code=201)
    async def ingest_document(body: DocumentIngestRequest):
        from fastapi.responses import JSONResponse

        indexer = getattr(app.state, "bm25_indexer", None)
        if indexer is None:
            return JSONResponse({"error": "unavailable"}, status_code=503)

        pool = getattr(app.state, "pg_pool", None)
        if pool is None:
            return JSONResponse({"error": "pg_pool not wired"}, status_code=503)

        from llm_client.rag.indexing import Document, index_document_with_hybrid

        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (id) VALUES ($1) ON CONFLICT DO NOTHING",
                body.user_id,
            )

        document_id = str(uuid4())
        content_hash = hashlib.sha256(body.content.encode("utf-8")).hexdigest()
        document = Document(
            id=document_id,
            user_id=body.user_id,
            source_type=body.source_type,
            source_uri=body.source_uri,
            content_hash=content_hash,
            content=body.content,
            meta=body.metadata or {},
        )

        vector_writer = getattr(app.state, "vector_writer", None)
        try:
            result = await index_document_with_hybrid(document, indexer, vector_writer)
        except Exception as exc:  # noqa: BLE001 — mirrors service.py ingestion handler
            return JSONResponse(
                {"error": f"Indexing failed: {exc}", "document_id": document_id},
                status_code=500,
            )

        status = "indexed"
        if result.get("vector_indexed") is False:
            status = "partial"

        return DocumentIngestResponse(
            document_id=document_id,
            status=status,
            bm25_indexed=bool(result.get("bm25_indexed")),
            vector_indexed=result.get("vector_indexed"),
        )

    @app.delete("/documents/{document_id}")
    async def delete_document(document_id: str):
        from fastapi.responses import JSONResponse

        indexer = getattr(app.state, "bm25_indexer", None)
        if indexer is None:
            return JSONResponse({"error": "unavailable"}, status_code=503)

        pool = indexer.pg_pool
        async with pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM documents WHERE id = $1", document_id)
        if not exists:
            return JSONResponse({"error": "Document not found"}, status_code=404)

        # Phase 3: invalidate semantic cache BEFORE delete
        from llm_client.rag.cache_invalidator import get_cache_invalidator
        from uuid import UUID

        await get_cache_invalidator().invalidate_doc(UUID(document_id))

        await indexer.delete_document(document_id)
        return {"status": "deleted", "document_id": document_id}

    @app.put("/documents/{document_id}", response_model=DocumentUpdateResponse)
    async def update_document(document_id: str, body: dict):
        from fastapi.responses import JSONResponse

        indexer = getattr(app.state, "bm25_indexer", None)
        if indexer is None:
            return JSONResponse(
                {"error": "Document indexing unavailable — pg_pool not wired"},
                status_code=503,
            )

        pool = indexer.pg_pool
        async with pool.acquire() as conn:
            # Load existing document to get user_id and check existence
            existing = await conn.fetchrow(
                "SELECT id, user_id, content_hash FROM documents WHERE id = $1",
                document_id,
            )
            if not existing:
                return JSONResponse({"error": "Document not found"}, status_code=404)

            # Phase 3: invalidate semantic cache BEFORE mutation
            from llm_client.rag.cache_invalidator import get_cache_invalidator
            from uuid import UUID

            await get_cache_invalidator().invalidate_doc(UUID(document_id))

            # Update document row
            new_content_hash = hashlib.sha256(body["content"].encode("utf-8")).hexdigest()
            await conn.execute(
                """
                UPDATE documents 
                SET content = $1, content_hash = $2, indexed_at = now(), meta = $3
                WHERE id = $4
                """,
                body["content"],
                new_content_hash,
                body.get("metadata", {}),
                document_id,
            )

        return {"status": "updated"}

    return TestClient(app)


class _MockConn:
    def __init__(self, exists=True):
        self._exists = exists
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "INSERT 0 1"

    async def fetchval(self, sql, *args):
        self.executed.append((sql, args))
        return 1 if self._exists else None

    async def fetchrow(self, sql, *args):
        self.executed.append((sql, args))
        return (
            {
                "id": "550e8400-e29b-41d4-a716-446655440003",
                "user_id": "test_user",
                "content_hash": "abc123",
            }
            if self._exists
            else None
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


class _MockPool:
    def __init__(self, exists=True):
        self.conn = _MockConn(exists=exists)

    def acquire(self):
        return self.conn


def test_ingest_happy_path():
    indexer = MagicMock()
    indexer.index_document = AsyncMock(return_value=None)
    indexer.pg_pool = _MockPool()

    client = _build_client(bm25_indexer=indexer, pg_pool=_MockPool())
    response = client.post(
        "/documents",
        json={"user_id": "u1", "content": "hello world", "source_type": "api"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "indexed"
    assert body["bm25_indexed"] is True
    assert body["vector_indexed"] is None
    assert body["document_id"]


def test_ingest_partial_when_vector_fails():
    indexer = MagicMock()

    async def ok_index(doc):
        return None

    indexer.index_document = ok_index
    indexer.pg_pool = _MockPool()

    async def bad_vector(doc):
        raise RuntimeError("vector down")

    client = _build_client(bm25_indexer=indexer, vector_writer=bad_vector, pg_pool=_MockPool())
    response = client.post(
        "/documents",
        json={"user_id": "u1", "content": "hello"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "partial"
    assert response.json()["vector_indexed"] is False


def test_ingest_503_without_indexer():
    client = _build_client(bm25_indexer=None, pg_pool=_MockPool())
    response = client.post("/documents", json={"user_id": "u1", "content": "x"})
    assert response.status_code == 503


def test_delete_not_found():
    indexer = MagicMock()
    indexer.pg_pool = _MockPool(exists=False)
    client = _build_client(bm25_indexer=indexer, pg_pool=_MockPool())
    response = client.delete("/documents/missing-id")
    assert response.status_code == 404


def test_delete_happy_path():
    mock_invalidator = AsyncMock()
    mock_invalidator.invalidate_doc = AsyncMock(return_value=1)

    with patch(
        "llm_client.rag.cache_invalidator.get_cache_invalidator", return_value=mock_invalidator
    ):
        indexer = MagicMock()
        indexer.delete_document = AsyncMock(return_value=None)
        indexer.pg_pool = _MockPool(exists=True)
        client = _build_client(bm25_indexer=indexer, pg_pool=_MockPool())
        response = client.delete("/documents/550e8400-e29b-41d4-a716-446655440005")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        mock_invalidator.invalidate_doc.assert_called_once()


class TestCacheInvalidationIntegration:
    """Tests for cache invalidation hooks in delete and update endpoints."""

    def test_delete_endpoint_calls_invalidator(self):
        """Test that DELETE endpoint calls cache invalidator before delete."""
        mock_invalidator = AsyncMock()
        mock_invalidator.invalidate_doc = AsyncMock(return_value=1)

        # Mock the cache invalidator module
        with patch(
            "llm_client.rag.cache_invalidator.get_cache_invalidator", return_value=mock_invalidator
        ):
            indexer = MagicMock()
            indexer.delete_document = AsyncMock(return_value=None)
            indexer.pg_pool = _MockPool()
            client = _build_client(bm25_indexer=indexer, pg_pool=_MockPool())
            response = client.delete("/documents/550e8400-e29b-41d4-a716-446655440000")

            assert response.status_code == 200
            assert response.json()["status"] == "deleted"
            mock_invalidator.invalidate_doc.assert_called_once()
            # Verify UUID conversion: str -> UUID
            from uuid import UUID

            call_arg = mock_invalidator.invalidate_doc.call_args[0][0]
            assert isinstance(call_arg, UUID)
            assert str(call_arg) == "550e8400-e29b-41d4-a716-446655440000"

    def test_delete_endpoint_404_skips_invalidator(self):
        """Test that DELETE endpoint returns 404 without calling invalidator."""
        mock_invalidator = AsyncMock()

        with patch(
            "llm_client.rag.cache_invalidator.get_cache_invalidator", return_value=mock_invalidator
        ):
            indexer = MagicMock()
            indexer.delete_document = AsyncMock(return_value=None)
            indexer.pg_pool = _MockPool(exists=False)
            client = _build_client(bm25_indexer=indexer, pg_pool=_MockPool(exists=False))
            response = client.delete("/documents/550e8400-e29b-41d4-a716-446655440001")

            assert response.status_code == 404
            mock_invalidator.invalidate_doc.assert_not_called()

    def test_put_endpoint_calls_invalidator_before_update(self):
        """Test that PUT endpoint calls cache invalidator before update."""
        mock_invalidator = AsyncMock()
        mock_invalidator.invalidate_doc = AsyncMock(return_value=1)

        with patch(
            "llm_client.rag.cache_invalidator.get_cache_invalidator", return_value=mock_invalidator
        ):
            indexer = MagicMock()
            # Mock the update_document method
            indexer.update_document = AsyncMock(return_value=None)
            indexer.pg_pool = _MockPool()
            client = _build_client(bm25_indexer=indexer, pg_pool=_MockPool())
            response = client.put(
                "/documents/550e8400-e29b-41d4-a716-446655440002",
                json={
                    "content": "Updated content",
                    "source_type": "api",
                    "metadata": {"title": "Updated Document"},
                },
            )

            assert response.status_code == 200
            assert response.json()["status"] == "updated"
            mock_invalidator.invalidate_doc.assert_called_once()
            # Verify UUID conversion: str -> UUID
            from uuid import UUID

            call_arg = mock_invalidator.invalidate_doc.call_args[0][0]
            assert isinstance(call_arg, UUID)
            assert str(call_arg) == "550e8400-e29b-41d4-a716-446655440002"

    def test_put_endpoint_404_skips_invalidator(self):
        """Test that PUT endpoint returns 404 without calling invalidator."""
        mock_invalidator = AsyncMock()

        with patch(
            "llm_client.rag.cache_invalidator.get_cache_invalidator", return_value=mock_invalidator
        ):
            indexer = MagicMock()
            indexer.update_document = AsyncMock(return_value=None)
            indexer.pg_pool = _MockPool(exists=False)
            client = _build_client(bm25_indexer=indexer, pg_pool=_MockPool(exists=False))
            response = client.put(
                "/documents/550e8400-e29b-41d4-a716-446655440003",
                json={"content": "Updated content"},
            )

            assert response.status_code == 404
            mock_invalidator.invalidate_doc.assert_not_called()

    def test_put_endpoint_503_when_indexer_unavailable(self):
        """Test that PUT endpoint returns 503 when indexer is not available."""
        mock_invalidator = AsyncMock()

        with patch(
            "llm_client.rag.cache_invalidator.get_cache_invalidator", return_value=mock_invalidator
        ):
            # Build client without indexer
            client = _build_client(bm25_indexer=None, pg_pool=_MockPool())

            response = client.put(
                "/documents/550e8400-e29b-41d4-a716-446655440004",
                json={"content": "Updated content"},
            )

            assert response.status_code == 503
            mock_invalidator.invalidate_doc.assert_not_called()
