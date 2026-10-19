"""Tier-1 Facts Extractor (ADR-011 Phase 3).

Extracts atomic facts from documents at indexing time using LLM.
Stores facts in documents_facts table with embeddings for fast
retrieval.

Architecture: ARCHITECT.md v1.3.0 §5.2.5.
TRIZ: principle #17 (transition to another dimension — extraction
at index-time, not query-time); principle #9 (preliminary action).
"""

import json
import logging
from dataclasses import dataclass

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...config import settings
from ..indexing.models import Document, DocumentFact

logger = logging.getLogger(__name__)


FACT_EXTRACTION_PROMPT = """You are a fact extractor. Given the
document below, extract up to {max_facts} atomic, self-contained
facts. Each fact must be a single sentence that conveys a specific
piece of information from the document.

Rules:
- One fact = one sentence.
- Each fact must be self-contained (no "the document says" prefix).
- Skip trivial facts (e.g., "the document is about X").
- Skip opinions; only facts.
- Each fact must be attributable to a specific section/page if possible.

Document title: {title}
Document page: {page}
Document content (truncated to 5000 chars):
---
{content}
---

Return JSON array of objects with keys:
- "fact": string (the fact sentence)
- "section": string | null (section heading if identifiable)
- "page": int | null (page number)
- "confidence": float (0.0-1.0; how central is this fact to the doc)

Return ONLY the JSON array, no commentary.
"""


@dataclass
class ExtractedFact:
    fact: str
    section: str | None
    page: int | None
    confidence: float


class FactsExtractor:
    """Extracts atomic facts from a document via LLM, embeds them,
    and persists to documents_facts table."""

    def __init__(
        self,
        llm: ChatOpenAI,
        embeddings: OpenAIEmbeddings,
        max_facts_per_doc: int = 10,
        engine=None,
    ) -> None:
        self._llm = llm
        self._embeddings = embeddings
        self._max_facts = max_facts_per_doc
        self._engine = engine

    async def extract_from_document(
        self,
        document: Document,
        session: AsyncSession | None = None,
    ) -> list[DocumentFact]:
        """Extract facts from one document, embed them, persist."""
        # Skip if document already has facts (idempotent)
        if session is None:
            if self._engine is None:
                raise RuntimeError("No session provided and no internal engine")
            async_session_factory = async_sessionmaker(
                self._engine, class_=AsyncSession, expire_on_commit=False
            )
            async with async_session_factory() as db_session:
                return await self._extract_from_document_internal(document, db_session)

        return await self._extract_from_document_internal(document, session)

    async def _extract_from_document_internal(
        self,
        document: Document,
        session: AsyncSession,
    ) -> list[DocumentFact]:
        """Internal fact extraction with session."""
        result = await session.execute(
            select(DocumentFact).where(DocumentFact.document_id == document.id)
        )
        first_fact = result.scalars().first()
        if first_fact is not None:
            logger.debug("Doc %s already has facts — skip", document.id)
            return []

        # Truncate content (avoid huge LLM input)
        content = document.content[:5000] if document.content else ""
        if not content:
            logger.warning("Doc %s has empty content — skip fact extraction", document.id)
            return []

        # Get title/page from meta
        title = (document.meta or {}).get("title") or "(no title)"
        page = (document.meta or {}).get("page") or 0

        prompt = FACT_EXTRACTION_PROMPT.format(
            max_facts=self._max_facts,
            title=title,
            page=page,
            content=content,
        )

        # LLM call — gpt-4o-mini default, configurable
        response = await self._llm.ainvoke(prompt)
        try:
            # Strip markdown fences if present
            response_content = response.content
            if isinstance(response_content, list):
                response_content = str(response_content)
            response_content = response_content.strip()
            response_content = response_content.removeprefix("```json")
            response_content = response_content.removesuffix("```")
            response_content = response_content.strip()

            facts_raw = json.loads(response_content)
            if not isinstance(facts_raw, list):
                raise TypeError("Expected JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("LLM returned invalid JSON for doc %s: %s", document.id, e)
            return []

        # Embed all fact texts in one batch (cost optimization)
        fact_texts = [f["fact"][:500] for f in facts_raw[: self._max_facts]]
        for i, fact in enumerate(fact_texts):
            if len(fact) < len(facts_raw[i]["fact"]):
                logger.warning(
                    "Truncated fact %d from %d to 500 chars", i, len(facts_raw[i]["fact"])
                )

        embeddings = await self._embeddings.aembed_documents(fact_texts)

        # Persist
        doc_facts: list[DocumentFact] = []
        for raw, emb in zip(facts_raw[: self._max_facts], embeddings):
            fact = DocumentFact(
                document_id=document.id,
                fact_text=raw["fact"][:500],
                fact_embedding=emb,
                fact_metadata={
                    "section": raw.get("section"),
                    "page": raw.get("page"),
                    "confidence": raw.get("confidence", 0.5),
                },
                extractor_model=f"openai/{self._llm.model_name}",
            )
            session.add(fact)
            doc_facts.append(fact)

        await session.commit()
        logger.info(
            "Extracted %d facts from doc %s",
            len(doc_facts),
            document.id,
        )
        return doc_facts

    async def extract_batch(
        self,
        documents: list[Document],
        session: AsyncSession | None = None,
        batch_size: int = 5,
    ) -> dict[str, int]:
        """Extract facts from multiple documents in batches.
        Returns {document_id_str: extracted_count}.
        """
        if session is None:
            if self._engine is None:
                raise RuntimeError("No session provided and no internal engine")
            async_session_factory = async_sessionmaker(
                self._engine, class_=AsyncSession, expire_on_commit=False
            )
            async with async_session_factory() as db_session:
                return await self._extract_batch_internal(documents, db_session, batch_size)

        return await self._extract_batch_internal(documents, session, batch_size)

    async def _extract_batch_internal(
        self,
        documents: list[Document],
        session: AsyncSession,
        batch_size: int = 5,
    ) -> dict[str, int]:
        """Internal batch extraction with session."""
        results = {}
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            # Sequential within batch (avoid OpenAI rate limit), batch
            # gives amortized concurrency
            for doc in batch:
                try:
                    facts = await self._extract_from_document_internal(doc, session)
                    results[str(doc.id)] = len(facts)
                except RuntimeError as e:
                    logger.error("Failed to extract facts from doc %s: %s", doc.id, e)
                    results[str(doc.id)] = 0
        return results


_singleton: FactsExtractor | None = None


def get_facts_extractor() -> FactsExtractor | None:
    global _singleton
    if _singleton is not None:
        return _singleton
    s = settings
    if not s.facts_extraction_enabled:
        return None
    llm = ChatOpenAI(
        model=s.facts_extractor_model,
        temperature=0.0,
        api_key=SecretStr(s.openai_api_key) if s.openai_api_key else None,
    )
    embeddings = OpenAIEmbeddings(
        model=s.facts_embedding_model,
        api_key=SecretStr(s.openai_api_key) if s.openai_api_key else None,
    )

    # Create async engine if not provided
    engine = None
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(s.database_url.replace("postgresql+asyncpg://", "postgresql://"))

    _singleton = FactsExtractor(
        llm=llm,
        embeddings=embeddings,
        max_facts_per_doc=s.facts_extraction_max_facts_per_doc,
        engine=engine,
    )
    return _singleton
