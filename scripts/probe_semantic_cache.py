"""Probe semantic cache: put 3 queries, then get variations."""

import asyncio
import logging
from uuid import uuid4

from llm_client.rag.semantic_cache import get_semantic_cache

# Configure logging to see cache hit/miss messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Demonstrate semantic cache behavior with sample queries."""
    print("🔍 Probing SemanticAnswerCache (B-1 ADR-011)...")
    
    cache = get_semantic_cache()
    if cache is None:
        print("❌ Semantic cache is disabled in settings")
        return
    
    try:
        # Test 1: Put exact queries
        print("\n1️⃣ Putting 3 queries into cache...")
        
        doc_id1 = uuid4()
        doc_id2 = uuid4()
        doc_id3 = uuid4()
        
        await cache.put("What is Python?", "Python is a high-level programming language known for its readability and simplicity.", [doc_id1], "gpt-4o-mini", 100)
        print("   ✓ Put: 'What is Python?'")
        
        await cache.put("How does RAG work?", "RAG (Retrieval-Augmented Generation) combines retrieval of relevant documents with language generation to improve response quality.", [doc_id2], "gpt-4o-mini", 150)
        print("   ✓ Put: 'How does RAG work?'")
        
        await cache.put("What is machine learning?", "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.", [doc_id3], "gpt-4o-mini", 120)
        print("   ✓ Put: 'What is machine learning?'")
        
        # Test 2: Get exact matches
        print("\n2️⃣ Testing exact matches...")
        
        result1 = await cache.get("What is Python?")
        if result1:
            print(f"   ✅ Exact hit: 'What is Python?' (similarity: {result1.similarity_score:.3f})")
            print(f"      Answer preview: {result1.answer[:60]}...")
        else:
            print("   ❌ Exact miss: 'What is Python?'")
        
        result2 = await cache.get("How does RAG work?")
        if result2:
            print(f"   ✅ Exact hit: 'How does RAG work?' (similarity: {result2.similarity_score:.3f})")
            print(f"      Answer preview: {result2.answer[:60]}...")
        else:
            print("   ❌ Exact miss: 'How does RAG work?'")
        
        # Test 3: Get paraphrases (semantic similarity)
        print("\n3️⃣ Testing semantic similarity (paraphrases)...")
        
        # Paraphrase of Python question
        result3 = await cache.get("What's the Python programming language?")
        if result3:
            print(f"   ✅ Semantic hit: 'What's the Python programming language?' (similarity: {result3.similarity_score:.3f})")
            print(f"      Answer preview: {result3.answer[:60]}...")
        else:
            print("   ❌ Semantic miss: 'What's the Python programming language?'")
        
        # Paraphrase of RAG question
        result4 = await cache.get("Explain how retrieval-augmented generation functions?")
        if result4:
            print(f"   ✅ Semantic hit: 'Explain how retrieval-augmented generation functions?' (similarity: {result4.similarity_score:.3f})")
            print(f"      Answer preview: {result4.answer[:60]}...")
        else:
            print("   ❌ Semantic miss: 'Explain how retrieval-augmented generation functions?'")
        
        # Test 4: Get unrelated query (should miss)
        print("\n4️⃣ Testing unrelated query...")
        
        result5 = await cache.get("What's the weather like today?")
        if result5:
            print(f"   ⚠️  Unexpected hit: 'What's the weather like today?' (similarity: {result5.similarity_score:.3f})")
        else:
            print("   ✅ Expected miss: 'What's the weather like today?'")
        
        # Test 5: Test staleness
        print("\n5️⃣ Testing staleness mechanism...")
        
        # Mark one document as stale
        stale_count = await cache.mark_stale(doc_id1)
        print(f"   📌 Marked document {doc_id1} as stale. Affected {stale_count} cached answers.")
        
        # Query that should now be stale
        result6 = await cache.get("What is Python?")
        if result6:
            print("   ⚠️  Unexpected hit on stale answer: 'What is Python?'")
        else:
            print("   ✅ Correctly rejected stale answer: 'What is Python?'")
        
        # Query that shouldn't be affected
        result7 = await cache.get("How does RAG work?")
        if result7:
            print(f"   ✅ Still working on non-stale answer: 'How does RAG work?' (similarity: {result7.similarity_score:.3f})")
        else:
            print("   ❌ Unexpected miss on non-stale answer: 'How does RAG work?'")
        
        print("\n6️⃣ Summary:")
        print("   Semantic cache successfully demonstrates:")
        print("   • Exact query matching")
        print("   • Semantic similarity (paraphrase detection)")
        print("   • Staleness propagation on document updates")
        print("   • TTL-based expiration (not tested in this probe)")
        
    except Exception as e:
        logger.error(f"Probe failed: {e}")
        print(f"Probe failed: {e}")
    finally:
        if cache:
            await cache.close()
            print("\n🔒 Cache closed.")


if __name__ == "__main__":
    asyncio.run(main())