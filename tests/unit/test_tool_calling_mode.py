"""Unit tests for ToolCallingMode (Phase 3 ADR-016).

Tests enum parsing, case insensitivity, and capability-based defaults.
"""

import pytest

from llm_client.agent.capability_matrix import ModelCapabilities
from llm_client.agent.tool_calling_mode import ToolCallingMode

# ── Tests for from_string ─────────────────────────────────────────────────────


def test_from_string_native():
    """from_string("native") returns NATIVE."""
    mode = ToolCallingMode.from_string("native")
    assert mode == ToolCallingMode.NATIVE


def test_from_string_react_case_insensitive():
    """from_string("REACT") returns REACT."""
    mode = ToolCallingMode.from_string("REACT")
    assert mode == ToolCallingMode.REACT
    mode = ToolCallingMode.from_string("react")
    assert mode == ToolCallingMode.REACT
    mode = ToolCallingMode.from_string("  ReAcT  ")
    assert mode == ToolCallingMode.REACT


def test_from_string_invalid_raises():
    """from_string("unknown") raises ValueError."""
    with pytest.raises(ValueError, match="Unknown ToolCallingMode"):
        ToolCallingMode.from_string("unknown")


# ── Tests for default_for_capabilities ─────────────────────────────────────────


def test_default_for_capabilities_native_support_returns_hybrid():
    """caps.supports_native_tools=True → HYBRID."""
    caps = ModelCapabilities(
        supports_native_tools=True,
        supports_react_emulation=True,
    )
    mode = ToolCallingMode.default_for_capabilities(caps)
    assert mode == ToolCallingMode.HYBRID


def test_default_for_capabilities_no_native_returns_react():
    """supports_native_tools=False, supports_react_emulation=True → REACT."""
    caps = ModelCapabilities(
        supports_native_tools=False,
        supports_react_emulation=True,
    )
    mode = ToolCallingMode.default_for_capabilities(caps)
    assert mode == ToolCallingMode.REACT


def test_default_for_capabilities_neither_returns_react():
    """supports_native_tools=False, supports_react_emulation=False → REACT."""
    caps = ModelCapabilities(
        supports_native_tools=False,
        supports_react_emulation=False,
    )
    mode = ToolCallingMode.default_for_capabilities(caps)
    assert mode == ToolCallingMode.REACT
