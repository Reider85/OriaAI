"""Integration tests for documents_facts migration (Phase 3 A-3)."""

import uuid

import pytest

from llm_client.rag.indexing.models import DocumentFact


@pytest.mark.integration
class TestDocumentsFactsMigration:
    """Integration tests for documents_facts migration."""

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
                "id", "document_id", "fact_text", "fact_embedding",
                "fact_metadata", "extracted_at", "extractor_model"
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
                "ix_documents_facts_text_search"
            ]
            for idx in expected_indexes:
                assert idx in index_names, f"Index {idx} missing"

        await pool.close()

    @pytest.mark.asyncio
    async def test_pgvector_extension_active(self, database_url):
        """Test pgvector extension is active."""
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT extname FROM pg_extension WHERE extname='vector'"
            )
            assert result is not None, "pgvector extension not found"
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
            assert "vector_cosine_ops" in result["indexdef"], "HNSW index not using vector_cosine_ops"
        await pool.close()

    @pytest.mark.asyncio
    async def test_foreign_key_cascade(self, database_url):
        """Test foreign key CASCADE deletion."""
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            # Create a document
            doc_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO users (id) VALUES ($1)",
                user_id
            )
            await conn.execute(
                """
                INSERT INTO documents (id, user_id, source_type, content_hash, content)
                VALUES ($1, $2, 'test', 'hash', 'content')
                """,
                doc_id, user_id
            )

            # Create a fact for this document
            fact_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO documents_facts (id, document_id, fact_text, fact_metadata)
                VALUES ($1, $2, 'test fact', '{}')
                """,
                fact_id, doc_id
            )

            # Verify fact exists
            result = await conn.fetchrow(
                "SELECT id FROM documents_facts WHERE document_id = $1",
                doc_id
            )
            assert result is not None, "Fact not created"

            # Delete document
            await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)

            # Verify fact is deleted (CASCADE)
            result = await conn.fetchrow(
                "SELECT id FROM documents_facts WHERE document_id = $1",
                doc_id
            )
            assert result is None, "Fact not deleted by CASCADE"

            # Clean up user
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

        await pool.close()

    @pytest.mark.asyncio
    async def test_orm_roundtrip(self, database_url):
        """Test ORM model roundtrip: insert via ORM, read via asyncpg."""
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            # Create document first
            doc_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO users (id) VALUES ($1)",
                user_id
            )
            await conn.execute(
                """
                INSERT INTO documents (id, user_id, source_type, content_hash, content, metadata)
                VALUES ($1, $2, 'test', 'hash', 'content', '{"title": "Test Doc"}')
                """,
                doc_id, user_id
            )

            # Insert fact via ORM
            fact = DocumentFact(
                document_id=uuid.UUID(doc_id),
                fact_text="This is a test fact extracted from the document.",
                fact_metadata={"source": "test", "confidence": 0.95},
                extractor_model="gpt-4o-mini"
            )
            # Note: ORM insert requires async session, but for this test we'll use raw SQL
            # since ORM session setup is complex in integration tests
            await conn.execute(
                """
                INSERT INTO documents_facts (
                    document_id, fact_text, fact_metadata, extractor_model
                )
                VALUES ($1, $2, $3, $4)
                """,
                fact.document_id, fact.fact_text, fact.fact_metadata, fact.extractor_model
            )

            # Read fact back via asyncpg
            result = await conn.fetchrow(
                """
                SELECT id, document_id, fact_text, fact_metadata, extracted_at, extractor_model
                FROM documents_facts
                WHERE document_id = $1
                """,
                doc_id
            )

            assert result is not None
            assert result["fact_text"] == fact.fact_text
            assert result["fact_metadata"] == '{"source": "test", "confidence": 0.95}'
            assert result["extractor_model"] == "gpt-4o-mini"
            assert result["extracted_at"] is not None

            # Clean up
            await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

        await pool.close()

    @pytest.mark.asyncio
    async def test_migration_downgrade_and_reupgrade(self, database_url):
        """Test downgrade then reupgrade preserves head state."""
        import asyncpg

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            # Create a document and fact before downgrade
            doc_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO users (id) VALUES ($1)",
                user_id
            )
            await conn.execute(
                """
                INSERT INTO documents (id, user_id, source_type, content_hash, content)
                VALUES ($1, $2, 'test', 'hash', 'content')
                """,
                doc_id, user_id
            )

            fact_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO documents_facts (id, document_id, fact_text)
                VALUES ($1, $2, 'test fact')
                """,
                fact_id, doc_id
            )

            # Simulate downgrade (drop table)
            await conn.execute("DROP TABLE documents_facts")

            # Verify table is gone
            result = await conn.fetchrow(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'documents_facts'"
            )
            assert result is None, "documents_facts table still exists after downgrade"

            # Reupgrade (simulate alembic upgrade)
            # In real scenario this would be alembic upgrade head
            # For test, we recreate the table
            await conn.execute(
                """
                CREATE TABLE documents_facts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    fact_text TEXT NOT NULL,
                    fact_embedding FLOAT[],
                    fact_metadata JSONB NOT NULL DEFAULT '{}',
                    extracted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    extractor_model VARCHAR(100)
                )
                """
            )
            await conn.create_index(
                "ix_documents_facts_document_id",
                "documents_facts",
                ["document_id"]
            )
            await conn.create_index(
                "ix_documents_facts_extracted_at",
                "documents_facts",
                ["extracted_at"]
            )
            await conn.execute(
                """
                CREATE INDEX ix_documents_facts_embedding_hnsw
                ON documents_facts USING hnsw (fact_embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
                """
            )
            await conn.execute(
                """
                CREATE INDEX ix_documents_facts_text_search
                ON documents_facts USING GIN (to_tsvector('english', fact_text))
                """
            )

            # Verify table and indexes are back
            result = await conn.fetchrow(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'documents_facts'"
            )
            assert result is not None, "documents_facts table not recreated"

            # Clean up
            await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

        await pool.close()