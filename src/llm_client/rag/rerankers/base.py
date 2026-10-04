from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class RerankResult:
    doc_id: str
    score: float  # higher = more relevant
    original_index: int  # position in input list


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: Sequence[dict],  # each dict has at least "content" key
        top_k: int = 5,
        batch_size: int = 8,
    ) -> list[RerankResult]:
        """Returns top_k documents ranked by relevance to query."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for registry (e.g. 'bge-reranker-base')."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Returns True if reranker is ready to serve."""
        ...
