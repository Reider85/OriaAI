import os
from importlib.metadata import entry_points

from llm_client.rag.rerankers.base import Reranker


class RerankerNotFoundError(Exception):
    """Raised when requested reranker is not found in registry."""


class RerankerRegistry:
    """Registry for pluggable reranker implementations via entry points."""

    def __init__(self) -> None:
        self._instances: dict[str, Reranker] = {}
        self._available: list[str] | None = None

    def _load_available(self) -> list[str]:
        """Load available rerankers from entry points (cached)."""
        if self._available is None:
            try:
                eps = entry_points(group="llm_client.rerankers")
                self._available = [ep.name for ep in eps]
            except Exception:  # noqa: BLE001 — degrade to identity on any importlib failure
                # Fallback for environments without entry_points support
                self._available = ["identity"]  # identity always available
        return self._available

    def get(self, name: str) -> Reranker:
        """Get reranker instance by name (lazy singleton)."""
        if name not in self._instances:
            available = self._load_available()
            if name not in available:
                raise RerankerNotFoundError(f"Reranker '{name}' not found. Available: {available}")

            # Load instance via entry point
            eps = entry_points(group="llm_client.rerankers")
            for ep in eps:
                if ep.name == name:
                    self._instances[name] = ep.load()()
                    break
        return self._instances[name]

    def list_available(self) -> list[str]:
        """List all available reranker names."""
        return self._load_available()

    def get_default(self) -> Reranker:
        """Get default reranker (from RERANKER_DEFAULT env or first available)."""
        default_name = os.getenv("RERANKER_DEFAULT", "identity")
        
        # If Cohere is selected but no API key is available, fall back to BGE
        if default_name == "cohere" and not os.getenv("COHERE_API_KEY"):
            default_name = "bge"
        
        return self.get(default_name)


# Global registry instance
registry = RerankerRegistry()


# Convenience functions
def get_reranker(name: str) -> Reranker:
    """Get reranker by name."""
    return registry.get(name)


def list_available_rerankers() -> list[str]:
    """List available reranker names."""
    return registry.list_available()


def get_default_reranker() -> Reranker:
    """Get default reranker."""
    return registry.get_default()
