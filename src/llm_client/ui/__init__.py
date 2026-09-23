"""Streamlit UI helpers (UI-0/UI-1, ADR-002/ADR-013).

``UIClient`` (UI-2) abstracts backend-specific rendering so that Phase 5 can
swap Streamlit for Chainlit without touching calling code.
"""

from .auto_cancel import AUTO_CANCEL_JS as AUTO_CANCEL_JS
from .auto_cancel import inject_auto_cancel as inject_auto_cancel
from .client import UIClient as UIClient
from .client import get_ui_client as get_ui_client
from .sidebar import render_sidebar as render_sidebar
from .streamlit_client import StreamlitClient as StreamlitClient

__all__ = [
    "AUTO_CANCEL_JS",
    "StreamlitClient",
    "UIClient",
    "get_ui_client",
    "inject_auto_cancel",
    "render_sidebar",
]