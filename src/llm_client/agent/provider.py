"""LLM provider factory + usage tracking + retry (AG-2, ARCHITECT §5.2.3).

Provides ``LLMProviderFactory`` that creates LangChain ``BaseChatModel`` instances
for supported providers (OpenAI, CUSTOM-OPENAI, ZAI in Phase 2).  Includes ``TokenUsageTracker``
callback handler and exponential-backoff retry decorator.

Phase 1: OpenAI only.  Anthropic / Ollama stubs raise ``NotImplementedError``.
Phase 2: CUSTOM-OPENAI (any OpenAI-compatible endpoint) + ZAI (z.ai).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ── Cost estimation — Phase 3 ADR-015: see model_cost_table.compute_call_cost ──


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
        provider: str = "openai",
        tool_calling_mode: str = "native",
    ) -> None:
        super().__init__()
        self._writer = operational_writer
        self._session_id = session_id
        self._pii_mask = pii_mask
        self._provider = provider
        self._tool_calling_mode = tool_calling_mode
        self._llm_start_time: float | None = None

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

        from .model_cost_table import compute_call_cost

        cost = compute_call_cost(self._provider, model, prompt_tokens, completion_tokens)

        # Calculate latency
        latency_seconds = 0.0
        if self._llm_start_time is not None:
            latency_seconds = time.monotonic() - self._llm_start_time

        # Record to Prometheus metrics (Phase 3 ADR-015)
        try:
            from ..observability.llm_metrics import record_llm_call
            record_llm_call(
                provider=self._provider,
                model=model,
                status="success" if response else "error",
                mode=self._tool_calling_mode,
                latency_seconds=latency_seconds,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
            )
        except Exception:
            logger.debug("Failed to record llm_usage metrics", exc_info=True)

        # Write to operational stream (existing D-2 logging)
        event: dict[str, Any] = {
            "event_type": "llm_usage",
            "provider": self._provider,
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

        # Record to CostGuard (Phase 3 ADR-015)
        try:
            from .cost_guard import get_cost_guard
            if await get_cost_guard().record_spend(cost):
                logger.warning("Cost guard triggered — router will switch to cheapest")
        except Exception:
            logger.debug("CostGuard.record_spend failed", exc_info=True)

        # Record success to circuit breaker (Phase 3 ADR-015)
        try:
            from .circuit_breaker import get_circuit_breaker
            await get_circuit_breaker().record_success(self._provider)
        except Exception:
            logger.debug("Circuit breaker record_success failed", exc_info=True)

    # LLM start callback — record start time for latency tracking
    def on_llm_start(self, serialized: dict[Any, Any], **kwargs: Any) -> None:
        """Record LLM start time for latency calculation."""
        self._llm_start_time = time.monotonic()

    # Chat model start callback — record start time for latency tracking
    def on_chat_model_start(self, serialized: dict[Any, Any], messages: list[Any], **kwargs: Any) -> None:
        """Record chat model start time for latency calculation."""
        self._llm_start_time = time.monotonic()

    # Error callback — record error status for circuit breaker
    async def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        """Record LLM error status for circuit breaker metrics."""
        # Extract model from kwargs if available
        model = kwargs.get("invocation_params", {}).get("model_name", "unknown")
        
        # Calculate latency (if start time was recorded)
        latency_seconds = 0.0
        if self._llm_start_time is not None:
            latency_seconds = time.monotonic() - self._llm_start_time
        
        # Record error status
        try:
            from ..observability.llm_metrics import record_llm_call
            record_llm_call(
                provider=self._provider,
                model=model,
                status="error",
                mode=self._tool_calling_mode,
                latency_seconds=latency_seconds,
            )
        except Exception:
            logger.debug("Failed to record llm_usage error metrics", exc_info=True)

        # Record failure to circuit breaker (Phase 3 ADR-015)
        try:
            from .circuit_breaker import get_circuit_breaker
            await get_circuit_breaker().record_failure(self._provider)
        except Exception:
            logger.debug("Circuit breaker record_failure failed", exc_info=True)


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
        retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
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
            One of ``"openai"``, ``"CUSTOM-OPENAI"``, ``"ZAI"``, ``"anthropic"`` (Phase 3), ``"ollama"`` (Phase 4).
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
                    api_key=SecretStr(api_key) if api_key else None,
                    **kwargs,
                )
            case "CUSTOM-OPENAI":
                # Extract base_url from kwargs to avoid duplication
                base_url = kwargs.pop("base_url", None)
                return ChatOpenAI(
                    model=model,
                    streaming=streaming,
                    api_key=SecretStr(api_key) if api_key else None,
                    base_url=base_url,
                    **kwargs,
                )
            case "ZAI":
                # Extract base_url from kwargs to avoid duplication
                base_url = kwargs.pop("base_url", None)

                # Check if OryaSecurity proxy is configured
                orya_proxy_url = kwargs.pop("orya_proxy_url", None)
                orya_proxy_key = kwargs.pop("orya_proxy_key", None)

                if orya_proxy_url:
                    # Use OryaSecurity as reverse proxy
                    logger.info(f"Using OryaSecurity proxy: {orya_proxy_url}")
                    # For reverse proxy, use the proxy URL as base_url and proxy key as API key
                    return ChatOpenAI(
                        model=model,
                        streaming=False,  # OryaSecurity doesn't support streaming properly
                        api_key=SecretStr(orya_proxy_key) if orya_proxy_key else None,
                        base_url=orya_proxy_url,
                        **kwargs,
                    )
                else:
                    # Direct connection to ZAI
                    return ChatOpenAI(
                        model=model,
                        streaming=streaming,
                        api_key=SecretStr(api_key) if api_key else None,
                        base_url=base_url,
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
