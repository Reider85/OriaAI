"""ToolCallingMode enum for ADR-016.

native: function calling API (OpenAI, Anthropic).
react:  system prompt emulation (Llama, Mistral via Ollama).
hybrid: native with fallback to react on parse error.

Architecture: ARCHITECT.md v1.3.0 §5.2.4 (Tool Layer).
TRIZ: principle #35 (parameter change — enum controls mode);
principle #13 (inverse — ReAct as base, native as optimization).
"""

from __future__ import annotations

from enum import Enum


class ToolCallingMode(str, Enum):
    NATIVE = "native"
    REACT = "react"
    HYBRID = "hybrid"

    @classmethod
    def from_string(cls, value: str) -> ToolCallingMode:
        """Parse string to enum, case-insensitive."""
        normalized = value.strip().lower()
        for mode in cls:
            if mode.value == normalized:
                return mode
        raise ValueError(
            f"Unknown ToolCallingMode: {value!r}. Must be one of: {[m.value for m in cls]}"
        )

    @classmethod
    def default_for_capabilities(cls, caps) -> ToolCallingMode:
        """Choose default mode based on ModelCapabilities (Блок D-1).
        - supports_native_tools=True → HYBRID (preferred; native with fallback)
        - supports_native_tools=False but supports_react_emulation=True → REACT
        - neither → REACT (best-effort; rarely fails)
        """
        if caps.supports_native_tools:
            return cls.HYBRID  # try native first, fall back to react
        elif caps.supports_react_emulation:
            return cls.REACT
        else:
            # Edge case: very small model, ReAct may fail; default to REACT
            # anyway (failure handled at runtime)
            return cls.REACT
