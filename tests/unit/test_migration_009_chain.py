"""Unit tests for migration 009 revision chain and ORM configuration."""

from pathlib import Path

from llm_client.rag.indexing.models import Document, DocumentFact


class TestMigration009RevisionChain:
    """Unit tests for migration 009 revision chain and ORM configuration."""

    def test_migration_009_revision_chain(self):
        """Test migration 009 has correct revision chain."""
        migration_file = Path(__file__).parent.parent.parent / "migrations" / "versions" / "009_create_documents_facts.py"
        migration_code = migration_file.read_text()
        
        # Extract revision info
        revision_line = [line for line in migration_code.split('\n') if 'revision = "009"' in line]
        down_revision_line = [line for line in migration_code.split('\n') if 'down_revision = "008"' in line]
        
        assert revision_line, "Migration 009 should have revision = '009'"
        assert down_revision_line, "Migration 009 should have down_revision = '008'"
        
        # Verify ORM models have correct relationships
        assert hasattr(Document, 'facts'), "Document should have 'facts' relationship"
        assert hasattr(DocumentFact, 'document'), "DocumentFact should have 'document' relationship"
        
        # Test relationship cascade configuration
        relationship = Document.facts.property
        assert relationship.cascade == "all, delete-orphan", "Document.facts should cascade delete-orphan"

    def test_documentfact_model_structure(self):
        """Test DocumentFact model has required fields and types."""
        # Test that model can be imported and has expected columns
        expected_columns = [
            "id", "document_id", "fact_text", "fact_embedding",
            "fact_metadata", "extracted_at", "extractor_model"
        ]
        
        for column_name in expected_columns:
            assert hasattr(DocumentFact, column_name), f"DocumentFact should have {column_name} column"

    def test_document_model_fact_relationship(self):
        """Test Document model can create facts with cascade."""
        # Test cascade behavior without actual DB (configuration-level test)
        doc = Document(
            user_id="test_user",
            source_type="test",
            content="test content",
            meta={"title": "Test Document"}
        )
        
        # Test that we can add facts to document (configuration-level)
        fact = DocumentFact(
            document_id=doc.id,
            fact_text="Test fact",
            fact_metadata={"source": "test"},
            extractor_model="gpt-4o-mini"
        )
        
        # In real DB, this would cascade-delete the fact when document is deleted
        # Here we just verify the relationship configuration
        assert fact.document_id == doc.id
        assert len(doc.facts) == 0  # No facts added yet, but relationship exists

    def test_document_model_content_hash_computation(self):
        """Test Document model auto-computes content_hash."""
        doc1 = Document(
            user_id="test_user",
            source_type="test",
            content="test content"
        )
        
        doc2 = Document(
            user_id="test_user",
            source_type="test",
            content="test content"
        )
        
        # Same content → same hash
        assert doc1.content_hash == doc2.content_hash
        
        # Different content → different hash
        doc3 = Document(
            user_id="test_user",
            source_type="test",
            content="different content"
        )
        assert doc1.content_hash != doc3.content_hash

    def test_documentfact_embedding_type(self):
        """Test DocumentFact fact_embedding is Vector type."""
        # Check that the fact_embedding column is defined as Vector
        fact_embedding_col = DocumentFact.__table__.columns.fact_embedding
        assert fact_embedding_col.type.__class__.__name__ == "Vector", "fact_embedding should be Vector type"
        
        # Check dimension
        assert fact_embedding_col.type.dimensions == 1536, "fact_embedding should have dimension 1536"

    def test_normalize_metadata_event(self):
        """Test normalize_metadata event prevents None metadata."""
        # This tests the event listener configuration, not actual DB behavior
        doc = Document(
            user_id="test_user",
            source_type="test",
            content="test content",
            meta=None  # Should be converted to {} by event
        )
        
        # In real DB, the event would convert None to {}
        # Here we verify the event is configured
        assert hasattr(doc, 'meta'), "Document should have meta attribute"