"""CacheAwareLLMClient — wrapper around BaseChatModel with
Tier-3 semantic cache check (ADR-011 Phase 3).

Implements BaseChatModel interface (LangChain), transparent to
graph. On ainvoke/astream: checks cache first; hit = return cached
response; miss = call underlying LLM, put result in cache.

Architecture: ARCHITECT.md v1.3.0 §5.2.5.
TRIZ: principle #16 (partial/excessive — cache intercepts part).
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

from .semantic_cache import get_semantic_cache

logger = logging.getLogger(__name__)

# Strong references to background tasks to prevent GC
_background_tasks: set[asyncio.Task] = set()


def _done_callback(task: asyncio.Task) -> None:
    """Remove completed tasks from the background set."""
    _background_tasks.discard(task)


def _store_in_cache_fire_and_forget(
    cache,
    query: str,
    answer: str,
    referenced_doc_ids: list[UUID],
    model: str,
    token_count: int,
) -> None:
    """Fire-and-forget cache put with background task tracking."""
    task = asyncio.create_task(
        cache.put(
            query=query,
            answer=answer,
            referenced_doc_ids=referenced_doc_ids,
            model=model,
            token_count=token_count,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_done_callback)


class CacheAwareLLMClient(BaseChatModel):
    """Wraps a BaseChatModel with semantic cache."""

    underlying: BaseChatModel
    model_config = {"arbitrary_types_allowed": True}  # noqa: RUF012

    def __init__(self, underlying: BaseChatModel, **kwargs):
        # BaseChatModel.__init__ handles pydantic fields
        super().__init__(underlying=underlying, **kwargs)

    @property
    def _llm_type(self) -> str:
        return f"cache-aware-{self.underlying._llm_type}"

    def bind_tools(self, tools: list, **kwargs):
        """Pass-through to underlying; bind_tools result is also a
        BaseChatModel, but we don't wrap it again (would double-cache).
        Tool-call decisions are made by underlying model; cache
        intercept only on final text generation."""
        bound = self.underlying.bind_tools(tools, **kwargs)
        # Wrap the bound model in a thin proxy that intercepts astream
        # but preserves bound tool-calling behavior.
        return CacheAwareBoundModel(bound=bound, cache_llm=self)

    def _extract_query(self, messages: list[BaseMessage]) -> str:
        """Extract the user query from messages for cache lookup."""
        # Use the last HumanMessage as the query
        for msg in reversed(messages):
            if msg.type == "human":
                return msg.content
        # Fallback: join all message contents (rare in agent context)
        return "\n".join(str(m.content) for m in messages)[:500]

    def get_semantic_cache(self):
        """Access to semantic cache for CacheAwareBoundModel."""
        return get_semantic_cache()

    def _extract_referenced_doc_ids(self, messages: list[BaseMessage]) -> list[UUID]:
        """Extract document_ids from ToolMessages in context
        (rag_query tool returns chunks with doc_id metadata)."""
        doc_ids: list[UUID] = []
        for msg in messages:
            if msg.type == "tool":
                # Primary path: artifact field (future-proof)
                if hasattr(msg, "artifact"):
                    for chunk in (msg.artifact or {}).get("chunks", []):
                        if "document_id" in chunk:
                            try:
                                doc_ids.append(UUID(chunk["document_id"]))
                            except (ValueError, TypeError):
                                continue

                # Fallback: parse content JSON (current graph flow)
                if hasattr(msg, "content") and msg.content:
                    try:
                        content_data = json.loads(msg.content)
                        chunks = content_data.get("chunks", [])
                        for chunk in chunks:
                            # Try multiple possible keys for document_id
                            for key in ["document_id", "doc_id", "id"]:
                                if key in chunk:
                                    try:
                                        doc_id = chunk[key]
                                        # If id is string, check if it looks like UUID
                                        if isinstance(doc_id, str) and len(doc_id) == 36:
                                            doc_ids.append(UUID(doc_id))
                                        elif isinstance(doc_id, str):
                                            # Try direct conversion for non-UUID strings
                                            doc_ids.append(UUID(doc_id))
                                        elif isinstance(doc_id, UUID):
                                            doc_ids.append(doc_id)
                                    except (ValueError, TypeError):
                                        continue
                            # Also check metadata.document_id
                            if "metadata" in chunk and isinstance(chunk["metadata"], dict):
                                metadata_doc_id = chunk["metadata"].get("document_id")
                                if metadata_doc_id:
                                    try:
                                        doc_ids.append(UUID(metadata_doc_id))
                                    except (ValueError, TypeError):
                                        continue
                    except (json.JSONDecodeError, TypeError):
                        # Content is not JSON, skip
                        continue
        return doc_ids

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> AIMessage:
        # type: ignore[override]  # BaseChatModel signature is complex, this matches usage in graph.py
        invoke_kwargs: dict[str, Any] = dict(kwargs)
        if stop is not None:
            invoke_kwargs["stop"] = stop
        if run_manager is not None:
            invoke_kwargs["run_manager"] = run_manager

        cache = get_semantic_cache()
        if cache is None:
            # Cache disabled — pass through
            return await self.underlying.ainvoke(messages, **invoke_kwargs)

        query = self._extract_query(messages)
        referenced_doc_ids = self._extract_referenced_doc_ids(messages)

        # Only cache answers that reference documents (RAG-grounded).
        # Pure-knowledge answers (empty referenced_doc_ids) are not
        # cached — they may differ for same query with different context.
        if not referenced_doc_ids:
            return await self.underlying.ainvoke(messages, **invoke_kwargs)

        hit = await cache.get(query)
        if hit is not None:
            # Cache HIT — return cached answer
            return AIMessage(content=hit.answer)

        # Cache MISS — call underlying LLM, cache the result
        result = await self.underlying.ainvoke(messages, **invoke_kwargs)
        answer = result.content

        # Determine token_count for cache value (best-effort)
        token_count = 0
        if hasattr(result, "llm_output") and result.llm_output:
            token_usage = result.llm_output.get("token_usage", {})
            token_count = token_usage.get("total_tokens", 0)

        # Persist in cache (fire-and-forget)
        _store_in_cache_fire_and_forget(
            cache=cache,
            query=query,
            answer=answer,
            referenced_doc_ids=referenced_doc_ids,
            model=self.underlying._identifying_params.get(
                "model_name", self.underlying._identifying_params.get("model", "unknown")
            ),
            token_count=token_count,
        )

        return result

    async def astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        config: Any | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessage]:
        # type: ignore[override]  # BaseChatModel signature is complex, this matches usage patterns
        """Stream with cache check. For cache HIT, we cannot truly
        stream (we have the full answer); we chunk it into words."""
        cache = get_semantic_cache()
        if cache is None:
            async for chunk in self.underlying.astream(
                messages, stop=stop, config=config, **kwargs
            ):
                yield chunk
            return

        query = self._extract_query(messages)
        referenced_doc_ids = self._extract_referenced_doc_ids(messages)
        if not referenced_doc_ids:
            async for chunk in self.underlying.astream(
                messages, stop=stop, config=config, **kwargs
            ):
                yield chunk
            return

        hit = await cache.get(query)
        if hit is not None:
            # Simulate streaming by chunking the cached answer
            for word in hit.answer.split():
                yield AIMessage(content=word + " ")
            return

        # Cache MISS — stream from underlying, accumulate, then put
        chunks: list[str] = []
        async for chunk in self.underlying.astream(messages, stop=stop, config=config, **kwargs):
            chunks.append(str(chunk.content))
            yield chunk
        full_answer = "".join(chunks)

        # Determine token_count (unknown during stream)
        token_count = 0

        # Persist in cache (fire-and-forget)
        _store_in_cache_fire_and_forget(
            cache=cache,
            query=query,
            answer=full_answer,
            referenced_doc_ids=referenced_doc_ids,
            model=self.underlying._identifying_params.get(
                "model_name", self.underlying._identifying_params.get("model", "unknown")
            ),
            token_count=token_count,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Sync — fallback to underlying (no cache check, cache is async)
        return self.underlying._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class CacheAwareBoundModel:
    """Wraps a tool-bound LLM with cache check. The tool-bound LLM
    (returned by bind_tools) does NOT extend BaseChatModel cleanly
    in LangChain 0.3 (it's a Runnable, not a BaseChatModel). We
    proxy astream/ainvoke through cache."""

    def __init__(self, bound, cache_llm: "CacheAwareLLMClient"):
        self._bound = bound
        self._cache_llm = cache_llm

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> AIMessage:
        # Use cache_llm's cache logic, but call bound._call for
        # the actual LLM invocation (preserves tool-calling).
        cache = self._cache_llm.get_semantic_cache()
        if cache is None:
            # Cache disabled — pass through to bound model
            return await self._bound.ainvoke(messages, stop=stop, run_manager=run_manager, **kwargs)

        query = self._cache_llm._extract_query(messages)
        referenced_doc_ids = self._cache_llm._extract_referenced_doc_ids(messages)

        # Only cache answers that reference documents (RAG-grounded)
        if not referenced_doc_ids:
            return await self._bound.ainvoke(messages, stop=stop, run_manager=run_manager, **kwargs)

        hit = await cache.get(query)
        if hit is not None:
            # Cache HIT — return cached answer
            return AIMessage(content=hit.answer)

        # Cache MISS — call bound model, cache the result
        result = await self._bound.ainvoke(messages, stop=stop, run_manager=run_manager, **kwargs)
        answer = result.content

        # Determine token_count for cache value (best-effort)
        token_count = 0
        if hasattr(result, "llm_output") and result.llm_output:
            token_usage = result.llm_output.get("token_usage", {})
            token_count = token_usage.get("total_tokens", 0)

        # Persist in cache (fire-and-forget)
        _store_in_cache_fire_and_forget(
            cache=cache,
            query=query,
            answer=answer,
            referenced_doc_ids=referenced_doc_ids,
            model=self._bound._identifying_params.get(
                "model_name", self._bound._identifying_params.get("model", "unknown")
            ),
            token_count=token_count,
        )

        return result

    async def astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        config: Any | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessage]:
        """Stream with cache check. For cache HIT, we cannot truly
        stream (we have the full answer); we chunk it into words."""
        cache = self._cache_llm.get_semantic_cache()
        if cache is None:
            async for chunk in self._bound.astream(messages, stop=stop, config=config, **kwargs):
                yield chunk
            return

        query = self._cache_llm._extract_query(messages)
        referenced_doc_ids = self._cache_llm._extract_referenced_doc_ids(messages)
        if not referenced_doc_ids:
            async for chunk in self._bound.astream(messages, stop=stop, config=config, **kwargs):
                yield chunk
            return

        hit = await cache.get(query)
        if hit is not None:
            # Simulate streaming by chunking the cached answer
            for word in hit.answer.split():
                yield AIMessage(content=word + " ")
            return

        # Cache MISS — stream from bound, accumulate, then put
        chunks: list[str] = []
        async for chunk in self._bound.astream(messages, stop=stop, config=config, **kwargs):
            chunks.append(str(chunk.content))
            yield chunk
        full_answer = "".join(chunks)

        # Determine token_count (unknown during stream)
        token_count = 0

        # Persist in cache (fire-and-forget)
        _store_in_cache_fire_and_forget(
            cache=cache,
            query=query,
            answer=full_answer,
            referenced_doc_ids=referenced_doc_ids,
            model=self._bound._identifying_params.get(
                "model_name", self._bound._identifying_params.get("model", "unknown")
            ),
            token_count=token_count,
        )

    # Proxy other Runnable methods through to self._bound
    def __getattr__(self, name):
        return getattr(self._bound, name)
