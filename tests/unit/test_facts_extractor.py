"""Unit tests for FactsExtractor (ADR-011 Phase 3)."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from llm_client.rag.indexing.facts_extractor import FactsExtractor
from llm_client.rag.indexing.models import Document, DocumentFact


@pytest.fixture
def mock_llm():
    llm = MagicMock(spec="langchain_openai.ChatOpenAI")
    llm.model_name = "gpt-4o-mini"
    llm.ainvoke = AsyncMock()
    return llm


@pytest.fixture
def mock_embeddings():
    embeddings = MagicMock(spec="langchain_openai.OpenAIEmbeddings")
    embeddings.aembed_documents = AsyncMock(
        return_value=[[0.1, 0.2, 0.3] * 512]  # 1536-dim vector
    )
    return embeddings


@pytest.fixture
def sample_document():
    return Document(
        id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        source_type="file",
        content_hash="hash-1",
        content="Python is a programming language created by Guido van Rossum in 1991.",
        meta={"title": "Python History", "page": 1},
    )


@pytest.fixture
def empty_document():
    return Document(
        id="doc-2",
        user_id="user-1",
        source_type="file",
        content_hash="hash-2",
        content="",
        meta={},
    )


@pytest.mark.asyncio
async def test_extract_from_document_returns_facts(mock_llm, mock_embeddings, sample_document):
    """Test that facts extraction returns DocumentFact objects with embeddings."""
    # Mock LLM response
    facts_response = [
        {
            "fact": "Python is a programming language.",
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
    mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])

    extractor = FactsExtractor(
        llm=mock_llm,
        embeddings=mock_embeddings,
        max_facts_per_doc=10,
    )

    # Mock session
    session = AsyncMock()

    # Create a proper mock that mimics SQLAlchemy result
    class MockScalarResult:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    mock_scalars = MockScalarResult(None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.add = Mock()

    facts = await extractor.extract_from_document(sample_document, session)

    assert len(facts) == 2
    assert all(isinstance(fact, DocumentFact) for fact in facts)
    assert facts[0].fact_text == "Python is a programming language."
    assert facts[0].fact_metadata["section"] == "Introduction"
    assert facts[0].fact_metadata["confidence"] == 0.9
    assert facts[0].extractor_model == "openai/gpt-4o-mini"
    assert facts[0].fact_embedding is not None
    assert len(facts[0].fact_embedding) == 1536

    # Verify LLM was called with truncated content
    mock_llm.ainvoke.assert_called_once()
    call_args = mock_llm.ainvoke.call_args[0][0]
    assert "Python is a programming language created by Guido van Rossum in 1991." in call_args

    # Verify embeddings were called
    mock_embeddings.aembed_documents.assert_called_once()
    assert len(mock_embeddings.aembed_documents.call_args[0][0]) == 2

    # Verify session operations
    session.commit.assert_called_once()
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_extract_skips_if_already_extracted(mock_llm, mock_embeddings, sample_document):
    """Test that extraction is idempotent - skips if document already has facts."""
    extractor = FactsExtractor(
        llm=mock_llm,
        embeddings=mock_embeddings,
        max_facts_per_doc=10,
    )

    # Mock session with existing facts
    session = AsyncMock()
    mock_result = AsyncMock()
    mock_scalars = MagicMock()
    mock_first = AsyncMock(
        return_value=DocumentFact(
            id="fact-1",
            document_id=sample_document.id,
            fact_text="existing fact",
            fact_embedding=[0.1] * 1536,
            fact_metadata={},
            extracted_at="2026-01-01T00:00:00+00:00",
            extractor_model="openai/gpt-4o-mini",
        )
    )
    mock_scalars.first = mock_first
    mock_result.scalars = mock_scalars
    session.execute = AsyncMock(return_value=mock_result)

    facts = await extractor.extract_from_document(sample_document, session)

    assert len(facts) == 0
    mock_llm.ainvoke.assert_not_called()
    mock_embeddings.aembed_documents.assert_not_called()


@pytest.mark.asyncio
async def test_extract_handles_invalid_llm_response(mock_llm, mock_embeddings, sample_document):
    """Test that invalid LLM JSON response is handled gracefully."""

    # Mock invalid JSON response
    async def mock_invoke(prompt):
        return MagicMock(content="This is not valid JSON")

    mock_llm.ainvoke = mock_invoke

    extractor = FactsExtractor(
        llm=mock_llm,
        embeddings=mock_embeddings,
        max_facts_per_doc=10,
    )

    session = AsyncMock()

    # Create a proper mock that mimics SQLAlchemy result
    class MockScalarResult:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    mock_scalars = MockScalarResult(None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    session.execute = AsyncMock(return_value=mock_result)

    facts = await extractor.extract_from_document(sample_document, session)

    assert len(facts) == 0
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_extract_truncates_long_content(mock_llm, mock_embeddings):
    """Test that content is truncated to 5000 chars for LLM input."""
    long_content = "x" * 6000
    document = Document(
        id="00000000-0000-0000-0000-000000000003",
        user_id="user-1",
        source_type="file",
        content_hash="hash-3",
        content=long_content,
        meta={"title": "Long Document"},
    )

    mock_llm.ainvoke = AsyncMock()
    mock_llm.ainvoke.return_value.content = json.dumps(
        [{"fact": "This is a fact from a very long document.", "confidence": 0.9}]
    )

    extractor = FactsExtractor(
        llm=mock_llm,
        embeddings=mock_embeddings,
        max_facts_per_doc=10,
    )

    session = AsyncMock()

    # Create a proper mock that mimics SQLAlchemy result
    class MockScalarResult:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    mock_scalars = MockScalarResult(None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    session.execute = AsyncMock(return_value=mock_result)

    await extractor.extract_from_document(document, session)

    # Verify LLM received truncated content
    call_args = mock_llm.ainvoke.call_args[0][0]
    # The content should be truncated to 5000 chars
    # Look for the content between the --- markers
    lines = call_args.split("\n")
    in_content = False
    content_lines = []
    for line in lines:
        if line.strip() == "---":
            if not in_content:
                in_content = True
            else:
                break
        elif in_content:
            content_lines.append(line)

    content_part = "\n".join(content_lines)
    print(f"Content length: {len(content_part)}")
    assert len(content_part) == 5000
    assert content_part == "x" * 5000


@pytest.mark.asyncio
async def test_extract_batch_processes_in_batches(mock_llm, mock_embeddings):
    """Test that batch processing handles multiple documents in batches."""
    documents = [
        Document(
            id=f"00000000-0000-0000-0000-0000000000{i:02d}",
            user_id="user-1",
            source_type="file",
            content_hash=f"hash-{i}",
            content=f"Content {i}",
            meta={},
        )
        for i in range(12)
    ]

    mock_llm.ainvoke = AsyncMock()
    mock_llm.ainvoke.return_value.content = json.dumps(
        [{"fact": "Fact from test document", "confidence": 0.9}]
    )
    mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1] * 1536])

    extractor = FactsExtractor(
        llm=mock_llm,
        embeddings=mock_embeddings,
        max_facts_per_doc=10,
    )

    session = AsyncMock()

    # Create a proper mock that mimics SQLAlchemy result
    class MockScalarResult:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    mock_scalars = MockScalarResult(None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.add = Mock()

    results = await extractor.extract_batch(documents, session, batch_size=5)

    assert len(results) == 12
    assert all(count == 1 for count in results.values())
    assert mock_llm.ainvoke.call_count == 12  # 12 sequential calls
    assert mock_embeddings.aembed_documents.call_count == 12  # One per doc


@pytest.mark.asyncio
async def test_extract_metadata_includes_section_and_page(
    mock_llm, mock_embeddings, sample_document
):
    """Test that section and page metadata are properly extracted and stored."""
    facts_response = [
        {
            "fact": "Python is popular.",
            "section": "Introduction",
            "page": 1,
            "confidence": 0.9,
        },
        {
            "fact": "Python has many libraries.",
            "section": "Features",
            "page": 2,
            "confidence": 0.8,
        },
    ]
    mock_llm.ainvoke = AsyncMock()
    mock_llm.ainvoke.return_value.content = json.dumps(facts_response)
    mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])

    extractor = FactsExtractor(
        llm=mock_llm,
        embeddings=mock_embeddings,
        max_facts_per_doc=10,
    )

    session = AsyncMock()

    # Create a proper mock that mimics SQLAlchemy result
    class MockScalarResult:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    mock_scalars = MockScalarResult(None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.add = Mock()

    facts = await extractor.extract_from_document(sample_document, session)

    assert len(facts) == 2
    assert facts[0].fact_metadata["section"] == "Introduction"
    assert facts[0].fact_metadata["page"] == 1
    assert facts[0].fact_metadata["confidence"] == 0.9
    assert facts[1].fact_metadata["section"] == "Features"
    assert facts[1].fact_metadata["page"] == 2
    assert facts[1].fact_metadata["confidence"] == 0.8


@pytest.mark.asyncio
async def test_extract_truncates_fact_text_to_500(mock_llm, mock_embeddings):
    """Test that fact text is truncated to 500 chars with warning."""
    long_fact = "x" * 600
    facts_response = [{"fact": long_fact, "confidence": 0.9}]
    mock_llm.ainvoke = AsyncMock()
    mock_llm.ainvoke.return_value.content = json.dumps(facts_response)
    mock_embeddings.aembed_documents = AsyncMock(return_value=[[0.1] * 1536])

    extractor = FactsExtractor(
        llm=mock_llm,
        embeddings=mock_embeddings,
        max_facts_per_doc=10,
    )

    session = AsyncMock()

    # Create a proper mock that mimics SQLAlchemy result
    class MockScalarResult:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    mock_scalars = MockScalarResult(None)
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.add = Mock()

    # Execute extraction and check that facts are truncated
    facts = await extractor.extract_from_document(
        Document(
            id="00000000-0000-0000-0000-000000000004",
            user_id="user-1",
            source_type="file",
            content_hash="hash-4",
            content="Some content",
            meta={},
        ),
        session,
    )

    # Verify that fact text was truncated to 500 chars
    assert len(facts) == 1
    assert len(facts[0].fact_text) == 500
    assert facts[0].fact_text == "x" * 500

    # Verify fact was truncated
    session.add.assert_called()
    fact_text = session.add.call_args[0][0].fact_text
    assert len(fact_text) == 500
    assert fact_text == "x" * 500
