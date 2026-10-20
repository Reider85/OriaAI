"""Tier-3 Semantic Answer Cache (ADR-011 Phase 3).

Stores full LLM responses in Redis DB 2 keyed by query embedding.
Cosine similarity >0.92 = cache hit. TTL=24h. Invalidation via
referenced_doc_ids (see B-3 CacheInvalidator).

Architecture: ARCHITECT.md v1.3.0 §5.2.5 (RAG Layer three-tier
cache).
TRIZ: Standard 5.3.1 (производное вещество — semantic, не exact
match); principle #16 (частичное/избыточное — full cache, partial
invalidation); principle #21 (сканирование вперёд).
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import numpy as np
import redis.asyncio as redis
from langchain_openai import OpenAIEmbeddings

from ..config import settings
from ..observability.llm_metrics import record_cache_hit

logger = logging.getLogger(__name__)


@dataclass
class CacheHitResult:
    answer: str
    referenced_doc_ids: list[UUID]
    created_at: str
    model: str
    token_count: int
    similarity_score: float


class SemanticAnswerCache:
    """Tier-3 answer cache. Wraps LLM call ( planner node in
    build_agent_graph ) — see B-5 Pipeline integration."""

    EMBEDDING_NAMESPACE = "sem_cache:emb"
    ANSWER_NAMESPACE = "sem_cache:ans"

    def __init__(
        self,
        redis_client,
        embeddings: OpenAIEmbeddings,
        ttl_seconds: int = 86400,
        similarity_threshold: float = 0.92,
        max_entries: int = 10000,
    ) -> None:
        self._redis = redis_client
        self._embeddings = embeddings
        self._ttl = ttl_seconds
        self._threshold = similarity_threshold
        self._max_entries = max_entries

    async def get(self, query: str) -> CacheHitResult | None:
        """Check cache for semantically similar query. Returns
        CacheHitResult if cosine sim > threshold, else None."""
        query_emb = await self._embeddings.aembed_query(query)
        query_vec = np.array(query_emb, dtype=np.float32)

        # SCAN all embedding keys (O(N) but N <= max_entries=10k)
        # Phase 4 optimization: HNSW index in Redis Vector Library
        best_score = 0.0
        best_key: str | None = None
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match=f"{self.EMBEDDING_NAMESPACE}:*", count=500
            )
            if not keys:
                if cursor == 0:
                    break
                continue
            # MGET embeddings as bytes
            embeddings_raw = await self._redis.mget(keys)
            for key, raw in zip(keys, embeddings_raw):
                if raw is None:
                    continue
                cached_vec = np.frombuffer(cast(bytes, raw), dtype=np.float32)
                # cosine sim
                score = float(
                    np.dot(query_vec, cached_vec)
                    / (np.linalg.norm(query_vec) * np.linalg.norm(cached_vec) + 1e-9)
                )
                if score > best_score:
                    best_score = score
                    best_key = key.decode() if isinstance(key, bytes) else key
            if cursor == 0:
                break

        if best_key is None or best_score < self._threshold:
            record_cache_hit("miss")
            return None

        # Fetch answer by hash key (best_key = "sem_cache:emb:<hash>")
        hash_key = best_key.split(":", 2)[-1]
        answer_raw = await self._redis.get(f"{self.ANSWER_NAMESPACE}:{hash_key}")
        if answer_raw is None:
            # orphan embedding (answer evicted by LRU) — treat as miss
            record_cache_hit("miss")
            return None

        data = json.loads(answer_raw)
        # Staleness check (Блок B-3 invalidator мог mark stale)
        if data.get("stale", False):
            record_cache_hit("stale")
            return None

        record_cache_hit("hit")
        logger.info(
            "Semantic cache HIT query=%r score=%.4f hash=%s",
            query[:80],
            best_score,
            hash_key,
        )
        return CacheHitResult(
            answer=data["answer"],
            referenced_doc_ids=[UUID(d) for d in data.get("referenced_doc_ids", [])],
            created_at=data["created_at"],
            model=data["model"],
            token_count=data.get("token_count", 0),
            similarity_score=best_score,
        )

    async def put(
        self,
        query: str,
        answer: str,
        referenced_doc_ids: list[UUID],
        model: str,
        token_count: int,
    ) -> None:
        """Store LLM response in cache. Called after planner node
        completes astream (Блок B-5 integration)."""
        # Anti-pattern: don't cache answers that don't reference any documents
        if not referenced_doc_ids:
            logger.debug("Semantic cache skip: no referenced_doc_ids for query=%r", query[:80])
            return

        query_emb = await self._embeddings.aembed_query(query)
        vec_bytes = np.array(query_emb, dtype=np.float32).tobytes()
        hash_key = hashlib.sha256(vec_bytes).hexdigest()[:16]

        data = {
            "answer": answer,
            "referenced_doc_ids": [str(d) for d in referenced_doc_ids],
            "created_at": datetime.now(UTC).isoformat(),
            "model": model,
            "token_count": token_count,
            "stale": False,
        }
        pipe = self._redis.pipeline()
        pipe.set(
            f"{self.EMBEDDING_NAMESPACE}:{hash_key}",
            vec_bytes,
            ex=self._ttl,
        )
        pipe.set(
            f"{self.ANSWER_NAMESPACE}:{hash_key}",
            json.dumps(data),
            ex=self._ttl,
        )
        # Soft cap on entries (LRU eviction also at Redis level)
        await self._evict_if_needed(pipe)
        await pipe.execute()

    async def mark_stale(self, doc_id: UUID) -> int:
        """Mark all cached answers referencing doc_id as stale.
        Called from B-3 CacheInvalidator on document update."""
        count = 0
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor,
                match=f"{self.ANSWER_NAMESPACE}:*",
                count=500,
            )
            if not keys:
                if cursor == 0:
                    break
                continue
            raw_values = await self._redis.mget(keys)
            pipe = self._redis.pipeline()
            for key, raw in zip(keys, raw_values):
                if raw is None:
                    continue
                data = json.loads(raw)
                if str(doc_id) in data.get("referenced_doc_ids", []):
                    data["stale"] = True
                    pipe.set(key, json.dumps(data), ex=self._ttl)
                    count += 1
            await pipe.execute()
            if cursor == 0:
                break
        return count

    async def _evict_if_needed(self, pipe: redis.client.Pipeline) -> None:
        """Soft cap enforcement — if entries > max, delete oldest.
        NOTE: Redis LRU handles eviction; soft cap is safety net."""
        # Phase 4: use sorted set with timestamps for precise eviction
        # Phase 3: placeholder — rely on Redis allkeys-lru

    async def close(self) -> None:
        """Close Redis connection; reset singleton so next get_semantic_cache() creates a fresh instance."""
        global _singleton
        await self._redis.aclose()
        if _singleton is self:
            _singleton = None


_singleton: SemanticAnswerCache | None = None


def get_semantic_cache() -> SemanticAnswerCache | None:
    """Returns singleton SemanticAnswerCache or None if disabled."""
    global _singleton
    if not settings.semantic_cache_enabled:
        return None
    if _singleton is not None:
        return _singleton
    embeddings = OpenAIEmbeddings(model=settings.facts_embedding_model)
    redis_client = redis.from_url(settings.redis_semantic_cache_url)
    _singleton = SemanticAnswerCache(
        redis_client=redis_client,
        embeddings=embeddings,
        ttl_seconds=settings.semantic_cache_ttl_seconds,
        similarity_threshold=settings.semantic_cache_similarity_threshold,
        max_entries=settings.semantic_cache_max_entries,
    )
    return _singleton
