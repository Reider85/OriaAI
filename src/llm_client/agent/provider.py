"""LLM provider factory + usage tracking + retry (AG-2, ARCHITECT §5.2.3).

Provides ``LLMProviderFactory`` that creates LangChain ``BaseChatModel`` instances
for supported providers (OpenAI only in Phase 1).  Includes ``TokenUsageTracker``
callback handler and exponential-backoff retry decorator.

Phase 1: OpenAI only.  Anthropic / Ollama stubs raise ``NotImplementedError``.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ── Cost table (USD per 1M tokens) — Phase 1 hardcode, env-overridable later ──

_COST_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return estimated cost in USD for the given token counts."""
    prices = _COST_PER_1M.get(model)
    if prices is None:
        return 0.0
    return (prompt_tokens * prices["input"] + completion_tokens * prices["output"]) / 1_000_000


# ── Token usage tracker (D-2 operational logging) ─────────────────────────────


class TokenUsageTracker(BaseCallbackHandler):
    """Logs prompt/completion token counts and cost estimate after each LLM call.

    Writes to the ``OperationalStreamWriter`` (D-2).  Never logs prompt content
    or API keys — only usage *metrics* (token counts, model, session id).
    """

    def __init__(
        self,
        operational_writer: Any,
        session_id: str = "",
        *,
        pii_mask: bool = False,
    ) -> None:
        super().__init__()
        self._writer = operational_writer
        self._session_id = session_id
        self._pii_mask = pii_mask

    # BaseChatModel callback — fires after a successful LLM invocation
    async def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        llm_output = getattr(response, "llm_output", None) or {}

        # Handle both dict and object-style access
        if isinstance(llm_output, dict):
            token_usage = llm_output.get("token_usage") or {}
            model = llm_output.get("model_name", "unknown")
        else:
            token_usage = getattr(llm_output, "token_usage", None) or {}
            model = getattr(llm_output, "model_name", "unknown")

        if isinstance(token_usage, dict):
            prompt_tokens = token_usage.get("prompt_tokens", 0) or 0
            completion_tokens = token_usage.get("completion_tokens", 0) or 0
        else:
            prompt_tokens = getattr(token_usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(token_usage, "completion_tokens", 0) or 0

        cost = _estimate_cost(model, prompt_tokens, completion_tokens)

        event: dict[str, Any] = {
            "event_type": "llm_usage",
            "provider": "openai",
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_estimate_usd": round(cost, 8),
            "session_id": self._session_id,
        }
        try:
            await self._writer.write(event)
        except Exception:
            logger.debug("Failed to write llm_usage event", exc_info=True)


# ── Retry decorator (exponential backoff for transient LLM errors) ─────────────


def _before_sleep_log(retry_state: RetryCallState) -> None:
    """Log before sleeping between retries."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "LLM call failed (attempt %d), retrying in %.1fs: %s",
        retry_state.attempt_number,
        retry_state.next_action.sleep if retry_state.next_action else 0,
        exc,
    )


def create_retry_decorator(
    max_retries: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 8.0,
) -> Any:
    """Return a tenacity retry decorator for transient LLM API errors (429/500/503)."""
    return retry(
        retry=retry_if_exception_type(
            (TimeoutError, ConnectionError, OSError)
        ),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        stop=stop_after_attempt(max_retries),
        before_sleep=_before_sleep_log,
        reraise=True,
    )


# ── LLM Provider Factory (ARCHITECT §5.2.3) ─────────────────────────────────


class LLMProviderFactory:
    """Creates LangChain ``BaseChatModel`` instances for supported providers.

    Phase 1: OpenAI only.
    Phase 3: Anthropic (ADR-015 cost-aware router).
    Phase 4: Ollama (ADR-016 tool capability adapter).
    """

    @staticmethod
    def create(
        provider: str,
        model: str,
        *,
        api_key: str | None = None,
        streaming: bool = True,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Instantiate a chat model for *provider*.

        Parameters
        ----------
        provider:
            One of ``"openai"``, ``"anthropic"`` (Phase 3), ``"ollama"`` (Phase 4).
        model:
            Model identifier, e.g. ``"gpt-4o-mini"``.
        api_key:
            API key.  Caller (Settings) is responsible for loading it.
        streaming:
            Enable streaming responses (default ``True`` for SSE, ADR-007).
        **kwargs:
            Forwarded to the provider-specific chat model constructor.
        """
        match provider:
            case "openai":
                return ChatOpenAI(
                    model=model,
                    streaming=streaming,
                    api_key=api_key,
                    **kwargs,
                )
            case "anthropic":
                raise NotImplementedError(
                    "Anthropic provider is Phase 3 (ADR-015 cost-aware router)"
                )
            case "ollama":
                raise NotImplementedError(
                    "Ollama provider is Phase 4 (ADR-016 tool capability adapter)"
                )
            case _:
                raise ValueError(f"Unknown provider: {provider!r}")


__all__ = [
    "LLMProviderFactory",
    "TokenUsageTracker",
    "create_retry_decorator",
]
