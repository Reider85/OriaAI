"""Manual probe script for FactsExtractor (ADR-011 Phase 3).

Usage:
    python scripts/probe_facts_extractor.py

This script tests end-to-end fact extraction by:
1. Inserting a test document into the database
2. Running FactsExtractor on it
3. Verifying facts are stored in documents_facts table

Requires:
- PostgreSQL running on localhost:5434 (from .env)
- OPENAI_API_KEY set in environment (for LLM calls)
- facts_extraction_enabled=true in settings
"""
import asyncio
import logging
import uuid
from datetime import datetime

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from llm_client.config import get_settings
from llm_client.rag.indexing.facts_extractor import get_facts_extractor
from llm_client.rag.indexing.models import Document

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Run the facts extraction probe."""
    settings = get_settings()
    
    # Check if facts extraction is enabled
    if not settings.facts_extraction_enabled:
        logger.error("Facts extraction is disabled (FACTS_EXTRACTION_ENABLED=false)")
        return
    
    # Check if OpenAI API key is set
    if not settings.openai_api_key:
        logger.error("OPENAI_API_KEY not set in environment")
        return
    
    logger.info("Starting FactsExtractor probe...")
    
    # Create test document
    test_content = """Python is a high-level, interpreted programming language with dynamic semantics. 
    Its high-level built-in data structures, combined with dynamic typing and dynamic binding, 
    make it very attractive for Rapid Application Development, as well as for use as a scripting 
    or glue language to connect existing components together.
    
    Python's simple, easy to learn syntax emphasizes readability and therefore reduces the cost 
    of program maintenance. Python supports packages and modules, which encourages program 
    modularity and code reuse. The Python interpreter and the extensive standard library are 
    available in source or binary form without charge for all major platforms, and can be freely 
    distributed.
    
    Often, programmers fall in love with Python because of the increased productivity it provides. 
    Since there is no compilation step, the edit-test-debug cycle is incredibly fast. Debugging 
    Python programs is easy: a bad input will never cause a segmentation fault. Instead, it 
    raises an exception. When the program doesn't catch the exception, the interpreter prints 
    a stack trace. A source level debugger allows inspection of local and global variables, 
    evaluation of arbitrary expressions, setting breakpoints, stepping through a line at a 
    time, and so on.
    
    The debugger is written in Python itself, testifying to Python's introspective power. 
    On the other hand, often the quickest way to debug a program is to add a few print 
    statements to the source: the fast edit-test-debug cycle makes this simple approach 
    very effective."""
    
    document = Document(
        id=uuid.uuid4(),
        user_id="probe-user",
        source_type="file",
        source_uri="file:///tmp/python_history.txt",
        content_hash="probe-hash",
        content=test_content,
        meta={
            "title": "Python Programming Language",
            "author": "Guido van Rossum",
            "created_at": datetime.now().isoformat(),
            "tags": ["programming", "python", "tutorial"],
        },
    )
    
    # Connect to database and insert document
    try:
        # Create engine and session
        engine = create_async_engine(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
        async_session = sessionmaker(engine, class_=sessionmaker, expire_on_commit=False)
        
        async with async_session() as session:
            # Insert document
            session.add(document)
            await session.commit()
            logger.info(f"Inserted document {document.id}")
            
            # Get facts extractor
            extractor = get_facts_extractor()
            if extractor is None:
                logger.error("Failed to get FactsExtractor (disabled or misconfigured)")
                return
            
            # Extract facts
            logger.info("Extracting facts...")
            facts = await extractor.extract_from_document(document, session)
            
            if facts:
                logger.info(f"Successfully extracted {len(facts)} facts:")
                for i, fact in enumerate(facts, 1):
                    logger.info(f"  {i}. {fact.fact_text}")
                    logger.info(f"     Metadata: {fact.fact_metadata}")
                    logger.info(f"     Extracted at: {fact.extracted_at}")
            else:
                logger.warning("No facts extracted (document may already have facts)")
            
            # Query facts directly from database to verify persistence
            async with asyncpg.create_pool(
                settings.database_url.replace("postgresql+asyncpg://", "postgresql://"),
                min_size=1,
                max_size=1,
            ) as pool:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT id, fact_text, fact_metadata, extracted_at, extractor_model "
                        "FROM documents_facts WHERE document_id = $1",
                        str(document.id),
                    )
                    
                    logger.info(f"Found {len(rows)} facts in database:")
                    for row in rows:
                        logger.info(f"  DB Fact: {row['fact_text']}")
                        logger.info(f"  Metadata: {row['fact_metadata']}")
                        logger.info(f"  Extracted: {row['extracted_at']}")
                        logger.info(f"  Model: {row['extractor_model']}")
        
        logger.info("Probe completed successfully!")
        
    except Exception as e:
        logger.error(f"Probe failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())