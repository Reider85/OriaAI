"""RAG (Retrieval-Augmented Generation) pipeline with reranking after fusion."""

import logging
import time
from dataclasses import replace
from typing import Any

from llm_client.observability.forensic_writer import ForensicStreamWriter
from llm_client.observability.operational_writer import OperationalStreamWriter
from llm_client.rag.config import RetrievalStrategy, RetrieverConfig
from llm_client.rag.metrics import RerankerMetrics, default_reranker_metrics
from llm_client.rag.rerankers.chain import RerankerChain
from llm_client.rag.rerankers.registry import RerankerRegistry
from llm_client.rag.rerankers.registry import registry as default_reranker_registry
from llm_client.rag.retrieval import rrf_fusion

# Real RRF fusion function available in: from llm_client.rag.retrieval import rrf_fusion
# This _mock_rrf_fusion is kept for test isolation and backward compatibility

logger = logging.getLogger(__name__)


async def rerank_after_fusion(
    query: str,
    fused_docs: list[dict],  # top-50 after RRF fusion
    config: RetrieverConfig,
    *,
    reranker_registry: RerankerRegistry | None = None,
    metrics: RerankerMetrics | None = None,
    operational_writer: OperationalStreamWriter | None = None,
    forensic_writer: ForensicStreamWriter | None = None,
) -> list[dict]:
    """Apply reranking to documents after fusion in the RAG pipeline.

    Args:
        query: The search query
        fused_docs: Documents already fused (top-50 after RRF fusion)
        config: RetrieverConfig containing reranking settings
        reranker_registry: Optional registry (defaults to global registry)
        metrics: Optional metrics instance (defaults to global metrics)
        operational_writer: Optional operational writer for logging
        forensic_writer: Optional forensic writer for audit logging

    Returns:
        List of reranked documents (top-K based on config.reranker_top_k)

    Raises:
        ValueError: If config validation fails
        RuntimeError: If all rerankers fail and fallback is not possible
    """
    # Use global instances if not provided
    registry = reranker_registry or default_reranker_registry
    metrics = metrics or default_reranker_metrics

    # Early return if reranking is disabled or input is small enough
    if not config.reranker_enabled or len(fused_docs) <= config.reranker_top_k:
        metrics.set_input_count(len(fused_docs))
        metrics.set_output_count(len(fused_docs))
        return fused_docs[: config.reranker_top_k]

    # Record start time for latency measurement
    start_time = time.time()

    try:
        # Check if we should use a fallback chain
        if config.reranker_fallback_chain:
            # Build reranker chain from registry
            chain_rerankers = []
            for reranker_name in config.reranker_fallback_chain:
                try:
                    chain_rerankers.append(registry.get(reranker_name))
                except Exception as e:  # noqa: BLE001 — skip unloadable chain members
                    logger.warning(
                        "Failed to load reranker '%s' from fallback chain: %s",
                        reranker_name,
                        str(e),
                    )
                    continue

            if not chain_rerankers:
                logger.error("No valid rerankers found in fallback chain")
                metrics.increment_fallback_count(primary=config.reranker_name, active="identity")
                return _identity_fallback(fused_docs, config.reranker_top_k)

            reranker: Any = RerankerChain(chain_rerankers, metrics=metrics)
        else:
            # Use single reranker (existing behavior)
            reranker = registry.get(config.reranker_name)

        # Validate reranker health
        if not await reranker.health_check():
            logger.warning(
                "Reranker '%s' failed health check, falling back to identity", reranker.name
            )
            metrics.increment_fallback_count(primary=config.reranker_name, active="identity")
            # Log error to operational stream
            if operational_writer:
                await operational_writer.write(
                    {
                        "event": "rag_rerank_error",
                        "reranker": reranker.name,
                        "error": "Health check failed",
                        "input_count": len(fused_docs),
                    }
                )
            return _identity_fallback(fused_docs, config.reranker_top_k)

        # Record input count
        metrics.set_input_count(len(fused_docs))

        # Perform reranking
        results = await reranker.rerank(
            query=query,
            documents=fused_docs,
            top_k=config.reranker_top_k,
        )

        # Map back to original documents using original_index and add score
        reranked_docs = []
        for r in results:
            original_doc = fused_docs[r.original_index]
            reranked_doc = {
                "content": original_doc["content"],
                "metadata": original_doc.get("metadata", {}),
                "score": r.score,
            }
            if "id" in original_doc:
                reranked_doc["id"] = original_doc["id"]
            reranked_docs.append(reranked_doc)

        # Record metrics
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_latency(latency_ms)
        metrics.set_output_count(len(reranked_docs))

        # Log to operational stream
        if operational_writer:
            await operational_writer.write(
                {
                    "event": "rag_rerank",
                    "reranker": reranker.name,
                    "input_count": len(fused_docs),
                    "output_count": len(reranked_docs),
                    "latency_ms": round(latency_ms, 2),
                    "query": query,  # PII-safe: query is not sensitive
                }
            )

        # Log full rerank scores to forensic stream (for audit)
        if forensic_writer and forensic_writer._enabled:
            forensic_event = {
                "event": "rag_rerank_scores",
                "reranker": reranker.name,
                "query": query,
                "input_count": len(fused_docs),
                "output_count": len(reranked_docs),
                "scores": [
                    {
                        "doc_id": r.doc_id,
                        "score": r.score,
                        "original_index": r.original_index,
                    }
                    for r in results
                ],
            }
            await forensic_writer.write(forensic_event)

        return reranked_docs

    except Exception as e:  # noqa: BLE001 — intentional catch-all for graceful fallback
        # Log error and increment error counter
        logger.error("Reranking failed for query='%s', error=%s", query, str(e))
        metrics.increment_error_count()

        # Log to operational stream
        if operational_writer:
            await operational_writer.write(
                {
                    "event": "rag_rerank_error",
                    "reranker": config.reranker_name,
                    "error": str(e),
                    "input_count": len(fused_docs),
                }
            )

        # Fall back to identity reranking
        logger.warning("Falling back to identity reranking for query='%s'", query)
        metrics.increment_fallback_count(primary=config.reranker_name, active="identity")
        return _identity_fallback(fused_docs, config.reranker_top_k)


def _identity_fallback(fused_docs: list[dict], top_k: int) -> list[dict]:
    """Fallback identity reranking: return first top_k documents unchanged.

    Args:
        fused_docs: List of documents
        top_k: Number of documents to return

    Returns:
        First top_k documents from the input list with score=1.0
    """
    fallback_docs = []
    for doc in fused_docs[:top_k]:
        # The document id is preserved so the fallback keeps the same output
        # contract as the reranked path.
        fallback_doc = {
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
            "score": 1.0,  # Identity fallback gives neutral score
        }
        if "id" in doc:
            fallback_doc["id"] = doc["id"]
        fallback_docs.append(fallback_doc)
    return fallback_docs


async def _mock_rrf_fusion(
    vector_docs: list[dict], bm25_docs: list[dict], top_k: int = 50
) -> list[dict]:
    """Mock RRF fusion function for testing purposes.

    In the real implementation, this would be implemented in Block D-5.
    This mock simulates Reciprocal Rank Fusion by combining documents and
    assigning synthetic scores.

    Args:
        vector_docs: Documents from vector retrieval
        bm25_docs: Documents from BM25 retrieval
        top_k: Number of documents to return after fusion

    Returns:
        Fused documents with RRF scores
    """
    # Create a combined set of documents
    all_docs = {}

    # Add vector docs with synthetic scores
    for i, doc in enumerate(vector_docs):
        doc_id = doc.get("id", str(i))
        all_docs[doc_id] = {
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
            "vector_score": 1.0 / (i + 1),  # Synthetic RRF score
            "bm25_score": 0.0,
        }

    # Add BM25 docs with synthetic scores
    for i, doc in enumerate(bm25_docs):
        doc_id = doc.get("id", f"bm25_{i}")
        if doc_id in all_docs:
            all_docs[doc_id]["bm25_score"] = 1.0 / (i + 1)
        else:
            all_docs[doc_id] = {
                "content": doc["content"],
                "metadata": doc.get("metadata", {}),
                "vector_score": 0.0,
                "bm25_score": 1.0 / (i + 1),
            }

    # Apply RRF: score = 1 / (rank_vector + rank_bm25)
    fused_docs = []
    for doc_id, doc in all_docs.items():
        rrf_score = 1.0 / (doc["vector_score"] + doc["bm25_score"])
        fused_docs.append(
            {
                "id": doc_id,
                "content": doc["content"],
                "metadata": doc["metadata"],
                "score": rrf_score,
            }
        )

    # Sort by RRF score and return top_k
    fused_docs.sort(key=lambda x: x["score"], reverse=True)
    return fused_docs[:top_k]


# ── RagPipeline (AG-6, Phase 2) ──────────────────────────────────────────────


#: Maps G-4 UI settings keys onto ``RetrieverConfig`` fields. Anything outside
#: this mapping (``max_results`` targets web_search, ``tools_enabled`` the tool
#: layer) is intentionally ignored here.
_OVERRIDE_FIELDS = {
    "retrieval_strategy": "retrieval_strategy",
    "reranker": "reranker_name",
    "top_k": "reranker_top_k",
}


def _apply_retriever_overrides(
    config: RetrieverConfig,
    overrides: dict[str, Any] | None,
) -> RetrieverConfig:
    """Return a copy of *config* with the G-4 UI settings applied.

    Overrides arrive straight off the wire, so every value is validated before
    use: unparseable or non-positive entries are logged and dropped, and an
    override set that fails ``RetrieverConfig`` validation falls back to the
    unmodified env config rather than raising.
    """
    if not overrides:
        return config

    updates: dict[str, Any] = {}

    strategy = overrides.get("retrieval_strategy")
    if strategy is not None:
        try:
            updates["retrieval_strategy"] = RetrievalStrategy(strategy)
        except ValueError:
            logger.warning(
                "Unknown retrieval_strategy %r — keeping %s",
                strategy,
                config.retrieval_strategy.value,
            )

    reranker = overrides.get("reranker")
    if reranker is not None and str(reranker).strip():
        updates["reranker_name"] = str(reranker).strip()
    elif reranker is not None:
        logger.warning("Empty 'reranker' override — keeping %s", config.reranker_name)

    top_k = overrides.get("top_k")
    if top_k is not None:
        try:
            parsed_top_k = int(top_k)
        except (TypeError, ValueError):
            logger.warning(
                "Non-integer top_k override %r — keeping %s", top_k, config.reranker_top_k
            )
        else:
            if parsed_top_k > 0:
                updates["reranker_top_k"] = parsed_top_k
            else:
                logger.warning(
                    "Non-positive top_k override %r — keeping %s", top_k, config.reranker_top_k
                )

    if not updates:
        return config

    try:
        # replace() re-runs __post_init__, so the resulting config is validated.
        return replace(config, **updates)
    except ValueError as exc:
        logger.warning("RAG settings overrides rejected (%s) — using env config", exc)
        return config


def _build_retriever(config: RetrieverConfig, pg_pool: Any = None) -> Any:
    """Instantiate the retriever described by *config* (ADR-003 / ADR-020)."""
    from .retrieval import BM25Retriever, HybridRetriever
    from .retrieval.vector_store_factory import create_vector_retriever

    vector_retriever = create_vector_retriever(config)

    if config.retrieval_strategy == RetrievalStrategy.HYBRID:
        if vector_retriever is None and pg_pool is None:
            logger.warning(
                "HYBRID strategy requested but neither vector store nor pg_pool "
                "is available — returning empty retriever"
            )
            return _EmptyRetriever()
        if vector_retriever is None:
            logger.warning(
                "HYBRID strategy requested but no vector store available — degrading to BM25-only"
            )
            return BM25Retriever(pg_pool=pg_pool)
        return HybridRetriever(
            vector_retriever=vector_retriever,
            bm25_retriever=BM25Retriever(pg_pool=pg_pool),
            config=config,
        )

    if config.retrieval_strategy == RetrievalStrategy.BM25:
        if pg_pool is None:
            logger.warning("BM25 strategy requested but pg_pool is not wired")
            return _EmptyRetriever()
        return BM25Retriever(pg_pool=pg_pool)

    if vector_retriever is not None:
        return vector_retriever
    return _EmptyRetriever()


class RagPipeline:
    """Composes retriever + reranker based on RetrieverConfig.

    Lifecycle:
    - Created at agent-service startup (singleton, in-process).
    - retrieve(query, top_k) — called by rag_query tool and by
      rag_retriever node.
    - Vector store created via VectorStoreFactory (ADR-003).
    - Retriever: HybridRetriever (ADR-020), or vector-only — based on
      retrieval_strategy.
    - Reranker: BGE (ADR-017 default), Cohere (optional), or identity
      (disabled).
    """

    def __init__(
        self,
        retriever: Any,
        reranker_registry: RerankerRegistry,
        config: RetrieverConfig,
    ) -> None:
        self._retriever = retriever
        self._reranker_registry = reranker_registry
        self._config = config

    @classmethod
    def from_settings(
        cls,
        app_settings: Any,
        pg_pool: Any = None,
    ) -> "RagPipeline":
        """Factory method — called at agent-service startup.

        Reads RetrieverConfig from environment, creates the appropriate
        retriever (vector-only, hybrid, or BM25-only), and wires in the
        reranker registry.
        """
        return cls.from_settings_with_overrides(app_settings, None, pg_pool=pg_pool)

    @classmethod
    def from_settings_with_overrides(
        cls,
        app_settings: Any,
        overrides: dict[str, Any] | None = None,
        pg_pool: Any = None,
    ) -> "RagPipeline":
        """Build a pipeline from env config with per-request UI overrides (G-4).

        Environment config remains the baseline; ``overrides`` carries the
        retrieval knobs exposed by the UI settings panel — ``retrieval_strategy``
        (ADR-020), ``reranker`` (ADR-017), and ``top_k``. Unknown keys are
        ignored, invalid values are logged and dropped, and if an override would
        produce a config that fails validation the env config is kept intact.

        Args:
            app_settings: Application Settings. Used for pg_pool lookup when
                ``pg_pool`` is not passed explicitly.
            overrides: Optional per-request settings dict. None = env only.
            pg_pool: Optional asyncpg pool for BM25 retrieval. Falls back to
                ``app_settings.pg_pool`` then the shared singleton.
        """
        if pg_pool is None:
            from .pool import resolve_pool

            pg_pool = resolve_pool(app_settings)

        config = _apply_retriever_overrides(RetrieverConfig.from_env(), overrides)
        retriever = _build_retriever(config, pg_pool=pg_pool)

        return cls(
            retriever=retriever,
            reranker_registry=default_reranker_registry,
            config=config,
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve and rerank documents for a query.

        Args:
            query: Search query.
            top_k: Number of chunks after reranker.
            user_id: Optional tenant filter. None/empty retrieves across all
                users (dev-friendly); a real id scopes BM25 SQL.

        Returns:
            dict with keys: chunks, chunk_count, top_score, source_uris.
        """
        from .retrieval import HybridRetriever

        effective_user = user_id or ""

        # Step 1: Retrieval
        docs: list[dict[str, Any]] = []
        if isinstance(self._retriever, HybridRetriever):
            vector_docs, bm25_docs = await self._retriever.aretrieve(query, user_id=effective_user)
            docs = rrf_fusion(
                vector_docs,
                bm25_docs,
                top_k=self._config.hybrid_top_k,
                vector_weight=self._config.vector_weight,
                bm25_weight=self._config.bm25_weight,
            )
        elif hasattr(self._retriever, "aretrieve"):
            docs = await self._retriever.aretrieve(query, user_id=effective_user)
        elif hasattr(self._retriever, "aget_relevant_documents"):
            raw_docs = await self._retriever.aget_relevant_documents(query)
            docs = _normalize_langchain_docs(raw_docs)
        else:
            docs = []

        logger.info(
            "Retrieved %d docs (strategy=%s)",
            len(docs),
            self._config.retrieval_strategy,
        )

        # Step 2: Reranker (ADR-017)
        docs = await rerank_after_fusion(
            query,
            docs,
            self._config,
            reranker_registry=self._reranker_registry,
        )

        # Step 3: Format output
        chunks: list[dict[str, Any]] = []
        source_uris: list[str] = []
        for doc in docs:
            metadata = doc.get("metadata", {})
            source_uri = metadata.get("source_uri", "")
            title = metadata.get("title", source_uri)
            page = metadata.get("page")
            content_text = doc.get("content", "")
            content_preview = content_text[:200]
            if len(content_text) > 200:
                content_preview += "..."
            score = float(doc.get("score", 0.0))
            chunks.append(
                {
                    "source_uri": source_uri,
                    "title": title,
                    "page": page,
                    "content_preview": content_preview,
                    "score": score,
                }
            )
            if source_uri:
                source_uris.append(source_uri)

        top_score = chunks[0]["score"] if chunks else 0.0
        return {
            "chunks": chunks,
            "chunk_count": len(chunks),
            "top_score": top_score,
            "source_uris": source_uris,
        }


def _normalize_langchain_docs(raw_docs: list[Any]) -> list[dict[str, Any]]:
    """Convert LangChain Document objects to common dict format."""
    result = []
    for i, doc in enumerate(raw_docs):
        if hasattr(doc, "page_content"):
            content = doc.page_content
            metadata = getattr(doc, "metadata", {}) or {}
            score_val = getattr(doc, "score", None)
            score = float(score_val) if score_val is not None else 1.0 / (i + 1)
        else:
            content = str(doc)
            metadata = {}
            score = 1.0 / (i + 1)
        result.append({"content": content, "metadata": metadata, "score": score})
    return result


class _EmptyRetriever:
    """No-op retriever used when no vector store is configured."""

    async def aretrieve(self, query: str, user_id: str = "") -> list[dict[str, Any]]:
        return []

    async def aget_relevant_documents(self, query: str) -> list[Any]:
        return []
