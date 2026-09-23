"""LLM Client — Streamlit chat entry point (UI-0, ADR-002/ADR-007).

Run with ``streamlit run src/llm_client/ui/app.py`` (or ``python -m
llm_client.ui.app``). The app talks to the agent-service exclusively through
its SSE endpoints; the backend is never called directly from here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
from collections.abc import Iterator

import httpx
import streamlit as st

from llm_client.ui import chat, render, session, sidebar
from llm_client.ui.auto_cancel import inject_auto_cancel

APP_PORT_ENV = "APP_PORT"
APP_PORT_DEFAULT = "8501"
PENDING_ARTIFACTS_KEY = "pending_artifacts"
STREAM_TIMEOUT_ENV = "STREAM_TIMEOUT_SECONDS"
STREAM_TIMEOUT_DEFAULT = 60.0


def _stream_timeout() -> float:
    """Return the end-to-end streaming timeout from the environment (60 s)."""
    return float(os.getenv(STREAM_TIMEOUT_ENV, STREAM_TIMEOUT_DEFAULT))


def _stream_with_timeout(session_id: str) -> Iterator[str]:
    """Yield stream tokens but fail with a timeout badge if nothing arrives for
    ``STREAM_TIMEOUT_SECONDS`` (anti-pattern: spinner hanging forever)."""
    deadline = time.monotonic() + _stream_timeout()
    for token in chat.stream_tokens(session_id):
        if time.monotonic() > deadline:
            raise chat.ChatStreamError(
                "Timeout (no response)", status="error", detail="Timeout (no response)"
            )
        yield token


st.set_page_config(page_title="LLM Client", layout="wide")
st.title("LLM Client")

inject_auto_cancel()

session_id = session.init_state()

selected = sidebar.render_sidebar()
if selected is None:
    session.new_session()
    st.session_state[PENDING_ARTIFACTS_KEY] = []
    st.rerun()
elif selected != session_id:
    session.switch_session(selected)
    st.session_state[PENDING_ARTIFACTS_KEY] = []
    st.rerun()

render.render_history(session.get_messages())

for artifact in st.session_state.get(PENDING_ARTIFACTS_KEY, []):
    render.render_artifact_buttons([artifact])

prompt = st.chat_input("Type your message...")
if prompt:
    session.add_message(session_id, "user", prompt)
    render.render_message("user", prompt)

    with st.chat_message("assistant"):
        try:
            response = chat.send_message(session_id, prompt)
            response.raise_for_status()
        except httpx.HTTPError as exc:  # backend down -> st.error, no crash (UI-0 DoD)
            st.error(f"Agent service unavailable ({chat.agent_service_url()}): {exc}")
        else:
            chat.clear_pending_artifacts()
            status_ph = st.empty()
            token_area = st.empty()
            answer = ""
            try:
                with status_ph.container():
                    render.render_status_badge("streaming")
                for token in _stream_with_timeout(session_id):
                    answer += token
                    token_area.markdown(answer)
            except chat.ChatStreamError as exc:
                status_ph.empty()
                render.render_status_badge(
                    exc.status, exc.detail, traceback_text=traceback.format_exc()
                )
            else:
                status_ph.empty()
            if answer:
                session.add_message(session_id, "assistant", answer)
            artifacts = chat.get_pending_artifacts()
            if artifacts:
                st.session_state[PENDING_ARTIFACTS_KEY] = artifacts
                render.render_artifact_buttons(artifacts)


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
