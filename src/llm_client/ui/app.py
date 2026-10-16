"""LLM Client — Streamlit chat entry point (UI-0, ADR-002/ADR-007).

Run with ``streamlit run src/llm_client/ui/app.py`` (or ``python -m
llm_client.ui.app``). The app talks to the agent-service exclusively through
its SSE endpoints; the backend is never called directly from here.

All rendering goes through ``UIClient`` (get_ui_client()); direct ``st.*``
calls remain only where the operation is Streamlit-specific and has no
analogue in other backends (sidebar, status badges, page config).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import streamlit as st

# Load .env into environment variables (needed for AGENT_SERVICE_URL and others)
# python-dotenv is already a transitive dependency via pydantic-settings
print("Attempting to load .env...")
try:
    print("Importing dotenv...")
    from dotenv import find_dotenv, load_dotenv
    print("SUCCESS: dotenv imported successfully")
    
    # Try to find .env file
    print("Finding .env file...")
    env_file = find_dotenv(usecwd=True, raise_error_if_not_found=False)
    if env_file:
        print(f"Found .env at: {env_file}")
        load_dotenv(env_file, override=False)
        print("SUCCESS: Loaded .env")
        
        # Verify the load worked
        loaded_url = os.getenv("AGENT_SERVICE_URL", "NOT SET")
        print(f"After load, AGENT_SERVICE_URL: {loaded_url}")
    else:
        print("WARNING: .env file not found")
        
except ImportError as e:
    # dotenv not available, fallback (pydantic-settings Settings will still work if env vars are set)
    print(f"WARNING: python-dotenv not available: {e}")
    
    # Manual fallback: try to read .env directly
    try:
        env_file_path = Path(__file__).resolve().parents[3] / ".env"
        if env_file_path.exists():
            print(f"Manually reading .env from: {env_file_path}")
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('AGENT_SERVICE_URL='):
                        value = line.split('=', 1)[1].strip()
                        os.environ['AGENT_SERVICE_URL'] = value
                        print(f"SUCCESS: Manually set AGENT_SERVICE_URL: {value}")
                        break
    except OSError as e:
        print(f"WARNING: Manual fallback failed: {e}")
except OSError as e:
    print(f"WARNING: Error loading .env: {e}")

print("Continuing with app.py...")

from llm_client.types import ArtifactRef, MessageRole
from llm_client.ui import chat, session, sidebar
from llm_client.ui.auto_cancel import inject_auto_cancel
from llm_client.ui.client import get_ui_client
from llm_client.ui.render import render_settings_panel

APP_PORT_ENV = "APP_PORT"
APP_PORT_DEFAULT = "8501"
PENDING_ARTIFACTS_KEY = "pending_artifacts"

ArtifactFormat = Literal["md", "txt", "pdf", "docx", "odt", "xls", "xlsx"]
_ARTIFACT_FORMATS: tuple[str, ...] = ("md", "txt", "pdf", "docx", "odt", "xls", "xlsx")


def _artifact_format(raw: Any) -> ArtifactFormat:
    """Validate an ``artifact_ready`` format against supported outputs (ADR-008)."""
    fmt = str(raw or "md").lower()
    if fmt not in _ARTIFACT_FORMATS:
        fmt = "md"
    return cast(ArtifactFormat, fmt)


def _artifact_ref(artifact: dict[str, Any]) -> ArtifactRef:
    """Build an ``ArtifactRef`` from an ``artifact_ready`` SSE payload."""
    return ArtifactRef(
        artifact_id=str(artifact.get("artifact_id") or ""),
        format=_artifact_format(artifact.get("format")),
        filename=str(artifact.get("filename") or ""),
    )


st.set_page_config(page_title="LLM Client", layout="wide")
st.title("LLM Client")

client = get_ui_client()

session_id = session.init_state()

inject_auto_cancel(
    backend_origin=chat.agent_service_url(),
    session_id=session_id
)

# Streamlit-specific, not in UIClient interface.
selected = sidebar.render_sidebar()
settings = render_settings_panel(cast(MutableMapping[str, Any], st.session_state))
if selected is None:
    session.new_session()
    st.session_state[PENDING_ARTIFACTS_KEY] = []
    st.rerun()
elif selected == session.CLEAR_CONTEXT_ACTION:
    try:
        chat.clear_context(session_id)
    except httpx.HTTPError as e:
        st.warning(f"Failed to clear context: {e}")
    session.clear_context(session_id)
    st.session_state[PENDING_ARTIFACTS_KEY] = []
    st.rerun()
elif selected != session_id:
    session.switch_session(selected)
    st.session_state[PENDING_ARTIFACTS_KEY] = []
    st.rerun()

for message in session.get_messages():
    client.render_message(
        cast(MessageRole, str(message["role"])),
        str(message["content"]),
        message.get("metadata"),
    )

for artifact in st.session_state.get(PENDING_ARTIFACTS_KEY, []):
    client.render_artifact(_artifact_ref(artifact))

prompt = client.handle_user_input()
if prompt:
    user_message = session.add_message(session_id, "user", prompt)
    # Reset streaming state for new prompt (bugfix: streaming_done was never cleared)
    session.reset_streaming_state()
    # Streamlit-specific: st.empty() placeholder for the live PII badge.
    pii_badge_area = client.render_user_message(prompt)
    # Streaming handled inside @st.fragment — sidebar clicks do not interrupt.
    client.render_streaming_fragment(
        session_id, prompt, user_message, pii_badge_area, settings=settings
    )


def app_port() -> int:
    """Return ``APP_PORT`` from the environment (default 8501)."""
    return int(os.getenv(APP_PORT_ENV, APP_PORT_DEFAULT))


if __name__ == "__main__":
    sys.exit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                __file__,
                "--server.port",
                str(app_port()),
            ]
        )
    )
