"""Integration tests for documents_facts migration (Phase 3 A-3)."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from llm_client.rag.indexing.models import Base, Document, DocumentFact


@pytest.fixture(scope="class")
def alembic_config(database_url):
    """Alembic config for testing migrations."""
    # Path to alembic.ini
    alembic_ini_path = Path(__file__).parent.parent.parent / "alembic.ini"

    # Create alembic config
    config = Config(alembic_ini_path)
    config.set_main_option(
        "sqlalchemy.url", database_url.replace("postgresql+asyncpg://", "postgresql://")
    )

    return config


@pytest.fixture(scope="class")
def sync_engine(database_url):
    """Synchronous SQLAlchemy engine for ORM tests."""
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.mark.integration
class TestDocumentsFactsMigration:
    """Integration tests for documents_facts migration."""

    @pytest.mark.asyncio
    async def test_pgvector_extension_active(self, database_url):
        """Test pgvector extension is active."""
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            result = await conn.fetchrow("SELECT extname FROM pg_extension WHERE extname='vector'")
            assert result is not None, "pgvector extension not found"
        await pool.close()

    @pytest.mark.asyncio
    async def test_migration_upgrade_creates_table(self, database_url):
        """Test upgrade creates documents_facts table with correct schema."""
        import asyncpg

        # Test that table exists after upgrade
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            # Check table exists
            result = await conn.fetchrow(
                """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'documents_facts'
                """
            )
            assert result is not None, "documents_facts table not found"

            # Check columns exist
            columns = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'documents_facts'
                ORDER BY ordinal_position
                """
            )
            column_names = [row["column_name"] for row in columns]
            expected_columns = [
                "id",
                "document_id",
                "fact_text",
                "fact_embedding",
                "fact_metadata",
                "extracted_at",
                "extractor_model",
            ]
            for col in expected_columns:
                assert col in column_names, f"Column {col} missing"

            # Check indexes exist
            indexes = await conn.fetch(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'documents_facts'
                """
            )
            index_names = [row["indexname"] for row in indexes]
            expected_indexes = [
                "ix_documents_facts_document_id",
                "ix_documents_facts_extracted_at",
                "ix_documents_facts_embedding_hnsw",
                "ix_documents_facts_text_search",
            ]
            for idx in expected_indexes:
                assert idx in index_names, f"Index {idx} missing"

            # Check fact_embedding is vector type (not float[])
            result = await conn.fetchrow(
                """
                SELECT atttypid::regtype as vector_type
                FROM pg_attribute
                WHERE attrelid = 'documents_facts'::regclass
                AND attname = 'fact_embedding'
                """
            )
            assert result is not None, "fact_embedding column not found"
            assert result["vector_type"] == "vector", (
                f"fact_embedding should be vector type, got {result['vector_type']}"
            )

        await pool.close()

    @pytest.mark.asyncio
    async def test_hnsw_index_exists(self, database_url):
        """Test HNSW index on fact_embedding exists."""
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'documents_facts' 
                AND indexname = 'ix_documents_facts_embedding_hnsw'
                """
            )
            assert result is not None, "HNSW index ix_documents_facts_embedding_hnsw not found"
            assert "hnsw" in result["indexdef"], "HNSW index not using hnsw method"
            assert "vector_cosine_ops" in result["indexdef"], (
                "HNSW index not using vector_cosine_ops"
            )
        await pool.close()

    def test_alembic_upgrade_downgrade(self, alembic_config, database_url):
        """Test alembic upgrade and downgrade operations."""
        # Test upgrade to head
        command.upgrade(alembic_config, "head")

        # Test current revision
        current = command.current(alembic_config)
        assert current == "009", f"Current revision should be 009, got {current}"

        # Test downgrade to 008
        command.downgrade(alembic_config, "008")

        # Test current revision after downgrade
        current = command.current(alembic_config)
        assert current == "008", f"Current revision should be 008 after downgrade, got {current}"

        # Test upgrade back to head
        command.upgrade(alembic_config, "head")

        # Final check
        current = command.current(alembic_config)
        assert current == "009", f"Current revision should be 009 after re-upgrade, got {current}"

    @pytest.mark.asyncio
    async def test_foreign_key_cascade(self, database_url):
        """Test foreign key CASCADE deletion."""
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            # Create a document
            doc_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            await conn.execute("INSERT INTO users (id) VALUES ($1)", user_id)
            await conn.execute(
                """
                INSERT INTO documents (id, user_id, source_type, content_hash, content)
                VALUES ($1, $2, 'test', 'hash', 'content')
                """,
                doc_id,
                user_id,
            )

            # Create a fact for this document
            fact_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO documents_facts (id, document_id, fact_text, fact_metadata)
                VALUES ($1, $2, 'test fact', '{}')
                """,
                fact_id,
                doc_id,
            )

            # Verify fact exists
            result = await conn.fetchrow(
                "SELECT id FROM documents_facts WHERE document_id = $1", doc_id
            )
            assert result is not None, "Fact not created"

            # Delete document
            await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)

            # Verify fact is deleted (CASCADE)
            result = await conn.fetchrow(
                "SELECT id FROM documents_facts WHERE document_id = $1", doc_id
            )
            assert result is None, "Fact not deleted by CASCADE"

            # Clean up user
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

        await pool.close()

    def test_orm_roundtrip_with_session(self, sync_engine):
        """Test ORM model roundtrip: insert via ORM, read via ORM."""
        # Create tables
        Base.metadata.create_all(sync_engine)

        # Create session
        Session = sessionmaker(bind=sync_engine)
        session = Session()

        try:
            # Create document first
            doc = Document(
                user_id=str(uuid.uuid4()),
                source_type="test",
                content="Test document content",
                meta={"title": "Test Document"},
            )
            session.add(doc)
            session.commit()

            # Insert fact via ORM
            fact = DocumentFact(
                document_id=doc.id,
                fact_text="This is a test fact extracted from the document.",
                fact_metadata={"source": "test", "confidence": 0.95},
                extractor_model="gpt-4o-mini",
            )
            session.add(fact)
            session.commit()

            # Add embedding
            fact.fact_embedding = [0.1] * 1536  # 1536-dimensional vector
            session.commit()

            # Read fact back via ORM
            retrieved_fact = session.query(DocumentFact).filter_by(id=fact.id).first()

            assert retrieved_fact is not None
            assert retrieved_fact.fact_text == fact.fact_text
            assert retrieved_fact.fact_metadata == {"source": "test", "confidence": 0.95}
            assert retrieved_fact.extractor_model == "gpt-4o-mini"
            assert retrieved_fact.extracted_at is not None

            # Verify embedding
            assert retrieved_fact.fact_embedding is not None
            assert len(retrieved_fact.fact_embedding) == 1536
            assert retrieved_fact.fact_embedding[0] == 0.1

            # Verify relationship
            assert retrieved_fact.document.id == doc.id
            assert retrieved_fact.document.meta == {"title": "Test Document"}

            # Test cascade delete
            session.delete(doc)
            session.commit()

            # Verify fact is deleted
            deleted_fact = session.query(DocumentFact).filter_by(id=fact.id).first()
            assert deleted_fact is None, "Fact should be cascade-deleted"

        finally:
            session.close()
            # Clean up tables
            Base.metadata.drop_all(sync_engine)

    def test_orm_fact_embedding_vector_type(self, sync_engine):
        """Test that fact_embedding is properly stored as vector type."""
        # Create tables
        Base.metadata.create_all(sync_engine)

        # Create session
        Session = sessionmaker(bind=sync_engine)
        session = Session()

        try:
            # Create document
            doc = Document(user_id=str(uuid.uuid4()), source_type="test", content="Test content")
            session.add(doc)
            session.commit()

            # Create fact with embedding
            fact = DocumentFact(
                document_id=doc.id,
                fact_text="Test fact",
                fact_metadata={"test": True},
                extractor_model="gpt-4o-mini",
                fact_embedding=[0.5] * 1536,
            )
            session.add(fact)
            session.commit()

            # Verify embedding is stored as vector
            # Note: This tests ORM behavior, not actual vector storage format
            # The vector storage format is tested in test_hnsw_index_exists
            assert fact.fact_embedding is not None
            assert len(fact.fact_embedding) == 1536

        finally:
            session.close()
            Base.metadata.drop_all(sync_engine)

    @pytest.mark.asyncio
    async def test_migration_downgrade_and_reupgrade(self, alembic_config, database_url):
        """Test downgrade then reupgrade preserves head state."""
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            # Create a document and fact before downgrade
            doc_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            await conn.execute("INSERT INTO users (id) VALUES ($1)", user_id)
            await conn.execute(
                """
                INSERT INTO documents (id, user_id, source_type, content_hash, content)
                VALUES ($1, $2, 'test', 'hash', 'content')
                """,
                doc_id,
                user_id,
            )

            fact_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO documents_facts (id, document_id, fact_text)
                VALUES ($1, $2, 'test fact')
                """,
                fact_id,
                doc_id,
            )

            # Use alembic to downgrade (not raw SQL)
            command.downgrade(alembic_config, "008")

            # Verify table is gone
            result = await conn.fetchrow(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'documents_facts'"
            )
            assert result is None, "documents_facts table still exists after downgrade"

            # Use alembic to reupgrade
            command.upgrade(alembic_config, "head")

            # Verify table and indexes are back
            result = await conn.fetchrow(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'documents_facts'"
            )
            assert result is not None, "documents_facts table not recreated"

            # Verify HNSW index is back and working
            hnsw_result = await conn.fetchrow(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'documents_facts' 
                AND indexname = 'ix_documents_facts_embedding_hnsw'
                """
            )
            assert hnsw_result is not None, "HNSW index not recreated"
            assert "hnsw" in hnsw_result["indexdef"], "HNSW index not using hnsw method"
            assert "vector_cosine_ops" in hnsw_result["indexdef"], (
                "HNSW index not using vector_cosine_ops"
            )

            # Clean up
            await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

        await pool.close()
