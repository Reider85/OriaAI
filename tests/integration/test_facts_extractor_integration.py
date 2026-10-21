"""Integration tests for FactsExtractor (ADR-011 Phase 3)."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from llm_client.config import settings
from llm_client.rag.indexing.facts_extractor import FactsExtractor
from llm_client.rag.indexing.models import Document, DocumentFact


@pytest.mark.integration
class TestFactsExtractorIntegration:
    """End-to-end test of FactsExtractor with real PostgreSQL and mocked LLM."""

    @pytest.fixture
    def engine(self):
        """Create async engine for test database."""
        settings = get_settings()
        db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        return create_async_engine(db_url)

    @pytest.fixture
    def async_session(self, engine):
        """Create async session factory."""
        return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM that returns valid JSON."""
        llm = MagicMock()
        llm.model_name = "gpt-4o-mini"
        llm.ainvoke = AsyncMock()
        return llm

    @pytest.fixture
    def mock_embeddings(self):
        """Mock embeddings that return fixed vector."""
        embeddings = MagicMock()
        embeddings.aembed_documents = AsyncMock(
            return_value=[[0.1] * 1536]  # Fixed 1536-dim vector
        )
        return embeddings

    @pytest.fixture
    def document(self):
        """Create test document."""
        return Document(
            id=uuid.uuid4(),
            user_id="test-user",
            source_type="file",
            content_hash="test-hash",
            content="Python is a high-level programming language created by Guido van Rossum in 1991.",
            meta={"title": "Python Programming", "page": 1},
        )

    @pytest.mark.asyncio
    async def test_extract_from_document_full_flow(
        self, async_session, mock_llm, mock_embeddings, document
    ):
        """Test complete extraction flow: insert doc → extract → query facts."""
        # Insert document
        async with async_session() as session:
            session.add(document)
            await session.commit()

        # Mock LLM response
        facts_response = [
            {
                "fact": "Python is a high-level programming language.",
                "section": "Introduction",
                "page": 1,
                "confidence": 0.9,
            },
            {
                "fact": "Guido van Rossum created Python in 1991.",
                "section": "History",
                "page": 1,
                "confidence": 0.8,
            },
        ]
        mock_llm.ainvoke.return_value.content = json.dumps(facts_response)

        # Create extractor
        extractor = FactsExtractor(
            llm=mock_llm,
            embeddings=mock_embeddings,
            max_facts_per_doc=10,
        )

        # Extract facts
        async with async_session() as session:
            facts = await extractor.extract_from_document(document, session)

        # Verify extraction results
        assert len(facts) == 2
        assert all(isinstance(fact, DocumentFact) for fact in facts)

        # Verify first fact
        fact1 = facts[0]
        assert fact1.fact_text == "Python is a high-level programming language."
        assert fact1.fact_metadata["section"] == "Introduction"
        assert fact1.fact_metadata["page"] == 1
        assert fact1.fact_metadata["confidence"] == 0.9
        assert fact1.extractor_model == "openai/gpt-4o-mini"
        assert fact1.fact_embedding is not None
        assert len(fact1.fact_embedding) == 1536

        # Verify second fact
        fact2 = facts[1]
        assert fact2.fact_text == "Guido van Rossum created Python in 1991."
        assert fact2.fact_metadata["section"] == "History"
        assert fact2.fact_metadata["page"] == 1
        assert fact2.fact_metadata["confidence"] == 0.8

        # Verify LLM and embeddings were called
        mock_llm.ainvoke.assert_called_once()
        mock_embeddings.aembed_documents.assert_called_once()
        assert len(mock_embeddings.aembed_documents.call_args[0][0]) == 2

        # Query facts from database
        async with async_session() as session:
            db_facts = await session.execute(
                select(DocumentFact).where(DocumentFact.document_id == document.id)
            )
            db_facts = db_facts.scalars().all()

        assert len(db_facts) == 2
        assert db_facts[0].fact_text == "Python is a high-level programming language."
        assert db_facts[1].fact_text == "Guido van Rossum created Python in 1991."

    @pytest.mark.asyncio
    async def test_extract_skips_if_already_extracted(
        self, async_session, mock_llm, mock_embeddings, document
    ):
        """Test that extraction is idempotent with existing facts."""
        # Insert document and pre-existing fact
        async with async_session() as session:
            session.add(document)
            existing_fact = DocumentFact(
                document_id=document.id,
                fact_text="existing fact",
                fact_embedding=[0.1] * 1536,
                fact_metadata={"confidence": 0.5},
                extractor_model="openai/gpt-4o-mini",
            )
            session.add(existing_fact)
            await session.commit()

        # Create extractor
        extractor = FactsExtractor(
            llm=mock_llm,
            embeddings=mock_embeddings,
            max_facts_per_doc=10,
        )

        # Try to extract (should skip)
        async with async_session() as session:
            facts = await extractor.extract_from_document(document, session)

        # Should return empty list (idempotent)
        assert len(facts) == 0

        # LLM should not be called
        mock_llm.ainvoke.assert_not_called()
        mock_embeddings.aembed_documents.assert_not_called()

        # Verify no duplicate facts in database
        async with async_session() as session:
            count = await session.execute(
                select(DocumentFact).where(DocumentFact.document_id == document.id)
            )
            count = count.scalars().all()
            assert len(count) == 1  # Only the original fact

    @pytest.mark.asyncio
    async def test_extract_handles_empty_content(self, async_session, mock_llm, mock_embeddings):
        """Test that empty content is handled gracefully."""
        empty_doc = Document(
            id=uuid.uuid4(),
            user_id="test-user",
            source_type="file",
            content_hash="empty-hash",
            content="",
            meta={},
        )

        # Create extractor
        extractor = FactsExtractor(
            llm=mock_llm,
            embeddings=mock_embeddings,
            max_facts_per_doc=10,
        )

        # Try to extract from empty document
        async with async_session() as session:
            session.add(empty_doc)
            await session.commit()

            facts = await extractor.extract_from_document(empty_doc, session)

        # Should return empty list
        assert len(facts) == 0

        # LLM should not be called
        mock_llm.ainvoke.assert_not_called()
        mock_embeddings.aembed_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_with_markdown_json_fence(
        self, async_session, mock_llm, mock_embeddings, document
    ):
        """Test that JSON response with markdown fences is handled correctly."""
        # Mock LLM response with markdown fences
        facts_response = [{"fact": "Python is versatile.", "confidence": 0.9}]
        mock_llm.ainvoke.return_value.content = f"```json\n{json.dumps(facts_response)}\n```"

        # Create extractor
        extractor = FactsExtractor(
            llm=mock_llm,
            embeddings=mock_embeddings,
            max_facts_per_doc=10,
        )

        # Extract facts
        async with async_session() as session:
            session.add(document)
            await session.commit()
            facts = await extractor.extract_from_document(document, session)

        # Should extract successfully despite markdown fences
        assert len(facts) == 1
        assert facts[0].fact_text == "Python is versatile."
        mock_llm.ainvoke.assert_called_once()
        mock_embeddings.aembed_documents.assert_called_once()
