"""Local embeddings using SentenceTransformer for fallback when cloud embeddings are not configured."""

import asyncio
import logging
import os
from pathlib import Path

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class LocalSentenceTransformerEmbeddings:
    """Local embeddings using SentenceTransformer as fallback for RAG pipeline.
    
    Compatible with LangChain embedding interface for Chroma/PGVector.
    Uses BGE-m3 by default (1024-dim multilingual embeddings).
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        model_dir: str | None = None,
        device: str = "cpu",
        batch_size: int = 32,
        **kwargs
    ):
        self._model: SentenceTransformer | None = None
        self._model_name = model_name
        self._model_dir = model_dir or os.getenv("LOCAL_EMBEDDING_MODEL_DIR", "./models/bge-m3")
        self._device = device or os.getenv("LOCAL_EMBEDDING_DEVICE", "cpu")
        self._batch_size = batch_size or int(os.getenv("LOCAL_EMBEDDING_BATCH_SIZE", "32"))
        self._model_path = Path(self._model_dir or "./models/bge-m3")

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the model on first access."""
        if self._model is None:
            self._model = self._ensure_loaded()
        return self._model

    def _ensure_loaded(self) -> SentenceTransformer:
        """Load the SentenceTransformer model from local directory if available, else from HF hub."""
        try:
            # Try loading from local directory first (faster, no network)
            if self._model_path.exists() and (self._model_path / "config.json").exists():
                logger.info(f"Loading local embedding model from {self._model_path}")
                model = SentenceTransformer(str(self._model_path), device=self._device)
            else:
                # Fallback to downloading from HF hub (should not happen if download script ran)
                logger.warning(
                    f"Local model not found at {self._model_path}, downloading {self._model_name}"
                )
                self._model_path.mkdir(parents=True, exist_ok=True)
                model = SentenceTransformer(
                    self._model_name,
                    device=self._device,
                    cache_folder=str(self._model_path.parent)
                )
            return model
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents (texts).
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embeddings (each embedding is a list of floats)
        """
        if not texts:
            return []
        
        try:
            embeddings = self.model.encode(
                texts,
                show_progress_bar=False,
                convert_to_numpy=True,
                convert_to_tensor=False
            ).tolist()
            return embeddings
        except Exception as e:
            logger.error(f"Error embedding documents: {e}")
            raise

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query text.
        
        Args:
            text: Single text string to embed
            
        Returns:
            Embedding as a list of floats
        """
        try:
            embedding = self.model.encode(
                text,
                show_progress_bar=False,
                convert_to_numpy=True,
                convert_to_tensor=False
            ).tolist()
            return embedding
        except Exception as e:
            logger.error(f"Error embedding query: {e}")
            raise

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Async version of embed_documents."""
        # SentenceTransformer is CPU-bound, run in thread
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Async version of embed_query."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)

    def health_check(self) -> bool:
        """Check if the embedding model is healthy (can load and encode)."""
        try:
            # Test with a simple sentence
            test_embedding = self.embed_query("test")
            return len(test_embedding) > 0
        except (OSError, RuntimeError, ValueError):
            return False

    @property
    def dimension(self) -> int:
        """Get the embedding dimension."""
        # BGE-m3 produces 1024-dimensional embeddings
        return 1024