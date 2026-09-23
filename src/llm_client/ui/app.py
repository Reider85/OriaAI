"""LLM Client — Streamlit chat entry point (UI-0, ADR-002/ADR-007).

Run with ``streamlit run src/llm_client/ui/app.py`` (or ``python -m
llm_client.ui.app``). The app talks to the agent-service exclusively through
its SSE endpoints; the backend is never called directly from here.
"""

from __future__ import annotations

import os
import subprocess
import sys

import httpx
import streamlit as st  # type: ignore[import-untyped]

from llm_client.ui import chat, render, session, sidebar
from llm_client.ui.auto_cancel import inject_auto_cancel

APP_PORT_ENV = "APP_PORT"
APP_PORT_DEFAULT = "8501"

st.set_page_config(page_title="LLM Client", layout="wide")
st.title("LLM Client")

inject_auto_cancel()

session_id = session.init_state()

selected = sidebar.render_sidebar()
if selected is None:
    session.new_session()
    st.rerun()
elif selected != session_id:
    session.switch_session(selected)
    st.rerun()

render.render_history(session.get_messages())

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
            try:
                answer = "".join(st.write_stream(chat.stream_tokens(session_id)))
            except chat.ChatStreamError as exc:
                st.error(str(exc))
                answer = ""
            if answer:
                session.add_message(session_id, "assistant", answer)


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
