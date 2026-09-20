"""State-Delta Cycle Detection — preview without embeddings (Quick Win B-3).

Uses a simple text diff (difflib.SequenceMatcher) on the last 2 messages in the
LangGraph state. When similarity stays above CYCLE_DETECTION_THRESHOLD for two
consecutive iterations, flags ``cycle_detected`` for escalation.
"""
import difflib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def compute_state_delta(prev_state: dict, curr_state: dict) -> float:
    """Similarity score in [0, 1] between the last messages of two states.

    Compares only the last 2 messages — not the whole state (which may be large).
    """
    prev_messages = prev_state.get("messages") or []
    curr_messages = curr_state.get("messages") or []

    prev_text = _messages_text(prev_messages[-2:])
    curr_text = _messages_text(curr_messages[-2:])

    if not prev_text and not curr_text:
        return 1.0
    if not prev_text or not curr_text:
        return 0.0
    return difflib.SequenceMatcher(None, prev_text, curr_text).ratio()


def _messages_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "") or msg.get("text", "")
        else:
            content = getattr(msg, "content", "") or str(msg)
        if isinstance(content, list):  # content blocks (e.g. LangChain)
            parts.append(" ".join(str(c) for c in content))
        else:
            parts.append(str(content))
    return "\n".join(parts)


class IterationMonitor:
    """LangGraph callback that flags a cycle after N consecutive similar iterations.

    Config via env:
      CYCLE_DETECTION_ENABLED  (default true)
      CYCLE_DETECTION_THRESHOLD (default 0.95)
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        threshold: float | None = None,
        consecutive: int = 2,
    ) -> None:
        default_enabled = os.getenv("CYCLE_DETECTION_ENABLED", "true").lower() == "true"
        default_threshold = float(os.getenv("CYCLE_DETECTION_THRESHOLD", "0.95"))

        self._enabled = default_enabled if enabled is None else enabled
        self._threshold = default_threshold if threshold is None else threshold
        self._consecutive_required = consecutive
        self._consecutive_similar = 0
        self._prev_state: dict | None = None
        self._history: list[float] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def check(self, curr_state: dict) -> bool:
        """Inspect the current graph state. Returns True if a cycle was detected.

        When escalating, returns True and the graph should exit on the next
        conditional edge, returning the current answer as final.
        """
        if not self._enabled:
            return False

        executed = curr_state.get("_cycle_executed") or set()
        if "_iteration_monitor" in executed:
            return False
        executed = executed | {"_iteration_monitor"}

        if self._prev_state is None:
            self._prev_state = curr_state
            self._history.append(0.0)
            return False

        similarity = compute_state_delta(self._prev_state, curr_state)
        self._history.append(similarity)

        if similarity > self._threshold:
            self._consecutive_similar += 1
        else:
            self._consecutive_similar = 0

        self._prev_state = curr_state

        if self._consecutive_similar >= self._consecutive_required:
            logger.warning(
                "[cycle_detection] Cycle detected: similarity=%.3f (threshold=%.3f)",
                similarity,
                self._threshold,
            )
            return True
        return False

    @property
    def history(self) -> list[float]:
        return list(self._history)