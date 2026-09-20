"""Streamlit UI helpers for ADR-013: auto-cancel on tab close / visibility loss (C-5)."""

from .auto_cancel import AUTO_CANCEL_JS as AUTO_CANCEL_JS
from .auto_cancel import inject_auto_cancel as inject_auto_cancel

__all__ = ["AUTO_CANCEL_JS", "inject_auto_cancel"]