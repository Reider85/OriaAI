"""Rendering helpers for the Streamlit chat UI (UI-0, ADR-002/ADR-007).

Artifact download buttons (UI-1, ADR-008): ``render_artifact_buttons`` renders
one download button per ``artifact_ready`` event. Fast formats (md/txt) fetch
their content synchronously via ``GET /artifacts/{id}``; slow formats
(pdf/docx/odt/xls/xlsx) render a disabled placeholder while the backend is
still generating (503) with a retry path. These helpers are the Streamlit
implementation that ``StreamlitClient`` delegates to (prompt 8).

PII score badge (UI-1, ADR-014): ``render_pii_badge`` renders a compact,
color-coded badge next to a user message using the ``pii_score`` /
``pii_entities`` the backend reports via the SSE ``metadata`` event.

RAG citations panel (G-2, ADR-017/ADR-020): ``render_rag_citations`` renders
the chunks the agent retrieved through ``rag_query`` as one card per chunk —
clickable source link, meta line, relevance progress bar and a truncated
content preview — inside a collapsed ``@st.fragment`` expander.

Web search results panel (G-3, ADR-005/ADR-007): ``render_web_search_results``
renders the Tavily results the agent fetched through ``web_search`` as one card
per result — clickable title link, URL caption, snippet and an optional
relevance metric — inside its own collapsed ``@st.fragment`` expander, kept
separate from the RAG citations panel.
"""

from __future__ import annotations

import html
import math
import os
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, Literal, cast

import httpx

FAST_ARTIFACT_FORMATS = ("md", "txt")

CITATION_PREVIEW_CHARS = 200

PII_LOW_THRESHOLD_ENV = "PII_LOW_THRESHOLD"
PII_LOW_THRESHOLD_DEFAULT = 0.3
PII_HIGH_THRESHOLD_ENV = "PII_HIGH_THRESHOLD"
PII_HIGH_THRESHOLD_DEFAULT = 0.7

_BADGE_COLORS = {"low": "#2f9e44", "medium": "#f59f00", "high": "#e03131"}
_BADGE_LABELS = {"low": "PII: low", "medium": "PII: medium", "high": "PII: high"}

_MIME_BY_FORMAT = {
    "md": "text/markdown",
    "txt": "text/plain",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_ARTIFACT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)


def get_mime_type(fmt: str) -> str:
    """Map an artifact format to its MIME type (fallback: octet-stream)."""
    return _MIME_BY_FORMAT.get(fmt.lower(), "application/octet-stream")


def fetch_artifact_content(artifact_id: str) -> tuple[int, bytes | None]:
    """Fetch artifact bytes from ``GET /artifacts/{id}``.

    Returns ``(status_code, content)`` where content is ``None`` unless the
    status is 200. Transport failures surface as ``(0, None)``.
    """
    from llm_client.ui import chat

    url = f"{chat.agent_service_url()}/artifacts/{artifact_id}"
    try:
        response = httpx.get(url, timeout=_ARTIFACT_TIMEOUT)
    except httpx.HTTPError:
        return 0, None
    if response.status_code == 200:
        return 200, response.content
    return response.status_code, None


def render_artifact_buttons(artifacts: list[dict[str, Any]]) -> None:
    """Render one download button per artifact (ADR-008)."""
    for artifact in artifacts:
        _render_artifact_button(artifact)


def _render_artifact_button(artifact: dict[str, Any]) -> None:
    # Streamlit-specific widget rendering, imported lazily so the module stays
    # importable outside of a running Streamlit session.
    import streamlit as st

    artifact_id = str(artifact.get("artifact_id") or "")
    if not artifact_id:
        return
    fmt = str(artifact.get("format") or "").lower()
    filename = str(artifact.get("filename") or f"artifact-{artifact_id}.{fmt}")
    label = f"Download {fmt.upper() if fmt else 'artifact'}"
    mime = get_mime_type(fmt)

    status_code, content = fetch_artifact_content(artifact_id)
    if status_code == 404:
        st.warning(f"Artifact not found ({filename})")
        return
    if status_code == 200 and content is not None:
        st.download_button(
            label, data=content, file_name=filename, mime=mime
        )  # Streamlit-specific, not in UIClient interface.
        return

    # Slow path (pdf/docx/odt/xls/xlsx): still generating, non-blocking.
    if status_code == 503:
        st.warning("Still generating")
    disabled_label = f"{label} (Generating...)"
    st.download_button(
        disabled_label, data=b"", file_name=None, mime=mime, disabled=True
    )  # Streamlit-specific, not in UIClient interface.
    if st.button(f"Retry {filename}"):
        st.rerun()


def render_message(role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
    """Render a single chat message as a Streamlit bubbles + markdown block.

    When ``metadata`` carries a ``pii_score`` and ``role`` is ``"user"``, a
    compact PII badge is rendered after the content (ADR-014). PII badges are
    never rendered for assistant messages. Called by ``StreamlitClient``
    (behavior is backend-specific, outside the ``UIClient`` interface).
    """
    import streamlit as st

    with st.chat_message(role):  # Streamlit-specific, not in UIClient interface.
        st.markdown(content)
        if role == "user" and metadata:
            pii_score = metadata.get("pii_score")
            if pii_score is not None:
                render_pii_badge(
                    cast(float, pii_score),
                    metadata.get("pii_entities"),
                    message_id=str(metadata.get("message_id") or ""),
                )


def render_history(messages: list[dict[str, Any]]) -> None:
    """Render stored messages from the current session, in order."""
    for message in messages:
        render_message(
            str(message["role"]),
            str(message["content"]),
            message.get("metadata"),
        )


def render_error(message: str) -> None:
    """Render a non-fatal error banner (backend unavailable, stream failure)."""
    import streamlit as st

    st.error(message)


def render_status_badge(
    status: str,
    detail: str | None = None,
    traceback_text: str | None = None,
) -> None:
    """Render the LLM-call status indicator (UI-1, ADR-007/ADR-013).

    ``status`` is one of:

    * ``streaming`` — ``st.status`` spinner ``"Generating response..."``;
    * ``cancelled`` — red ``st.error`` ``"Cancelled: <detail>"`` (detail is the
      ``reason`` from the ADR-013 cancel event);
    * ``error`` — yellow ``st.warning`` ``"Error: <detail>"``; when
      ``traceback_text`` is given it goes into an expander, never inline.

    Uses ``st.status``/``st.empty`` only — never ``st.spinner`` (blocks re-run).
    The ``streaming`` badge is cleared by the caller via its placeholder.
    """
    import streamlit as st

    if status == "streaming":
        st.status("Generating response...", expanded=False)
        return
    if status == "cancelled":
        st.error("Cancelled" if detail is None else f"Cancelled: {detail}")
        return
    if status == "error":
        st.warning("Error" if detail is None else f"Error: {detail}")
        if traceback_text:
            with st.expander("Details"):
                st.code(traceback_text, language="python")
        return
    st.warning(f"Unknown status: {status}")


def pii_thresholds() -> tuple[float, float]:
    """Return ``(low, high)`` PII thresholds from the environment (ADR-014).

    ``PII_LOW_THRESHOLD`` (default 0.3) and ``PII_HIGH_THRESHOLD`` (default
    0.7) bound the low/medium/high bands. Never hardcoded in call sites.
    """
    low = float(os.getenv(PII_LOW_THRESHOLD_ENV, PII_LOW_THRESHOLD_DEFAULT))
    high = float(os.getenv(PII_HIGH_THRESHOLD_ENV, PII_HIGH_THRESHOLD_DEFAULT))
    return low, high


def pii_level(pii_score: float, low_threshold: float, high_threshold: float) -> str:
    """Map a PII score to ``low``/``medium``/``high`` (bounds inclusive)."""
    if pii_score >= high_threshold:
        return "high"
    if pii_score >= low_threshold:
        return "medium"
    return "low"


def entity_types_for_badge(
    pii_entities: Sequence[Any] | None,
) -> list[str]:
    """Normalize ``pii_entities`` (list of ``{"type": ...}`` dicts or strings)
    into a list of entity type names for the badge tooltip."""
    types: list[str] = []
    for entity in pii_entities or []:
        if isinstance(entity, Mapping):
            entity_type = entity.get("type")
            if entity_type:
                types.append(str(entity_type))
        elif isinstance(entity, str) and entity:
            types.append(entity)
    return types


def render_pii_badge(
    pii_score: float,
    pii_entities: Sequence[Any] | None = None,
    *,
    message_id: str | None = None,
    low_threshold: float | None = None,
    high_threshold: float | None = None,
) -> None:
    """Render a compact color-coded PII badge for a user message (UI-1, ADR-014).

    * ``< low``  -> green ``"PII: low"``;
    * ``low..high`` -> amber ``"PII: medium"``;
    * ``>= high`` -> red ``"PII: high"``.

    The detected entity types (e.g. ``["PERSON", "US_SSN"]``) are exposed as a
    native hover tooltip via the ``<span title=...>`` attribute, so the badge
    stays compact and never masks the original message text. Thresholds default
    to the environment (``PII_LOW_THRESHOLD`` / ``PII_HIGH_THRESHOLD``) and can
    be overridden per call for tests.
    """
    import streamlit as st

    if low_threshold is None or high_threshold is None:
        low_threshold, high_threshold = pii_thresholds()
    level = pii_level(pii_score, low_threshold, high_threshold)
    entities = entity_types_for_badge(pii_entities)
    st.markdown(
        _badge_markup(level, entities),
        unsafe_allow_html=True,
    )


def _badge_markup(level: str, entities: list[str]) -> str:
    color = _BADGE_COLORS[level]
    label = _BADGE_LABELS[level]
    title = f"Detected entities: {', '.join(entities)}" if entities else label
    escaped = html.escape(title, quote=True)
    return (
        f'<span title="{escaped}" style="background:{color};color:#fff;'
        f"padding:2px 8px;border-radius:10px;font-size:0.75em;"
        f'display:inline-block;">{label}</span>'
    )


def _escape_markdown_label(value: str) -> str:
    """Escape markdown link-label brackets so titles stay renderable."""
    return value.replace("[", "\\[").replace("]", "\\]")


def _citation_preview(content: Any, limit: int = CITATION_PREVIEW_CHARS) -> str:
    """Truncate a chunk preview to ``limit`` chars, appending ``"..."``.

    Chunks may carry PII or licensed text, so the full body is never rendered
    (G-2 anti-pattern).
    """
    text = str(content or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _citation_score(value: Any) -> float:
    """Normalize a relevance score to ``[0.0, 1.0]`` for the progress bar."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(score) or score < 0.0:
        return 0.0
    return min(score, 1.0)


def render_rag_citations(chunks: list[dict[str, Any]]) -> None:
    """Render the RAG citations panel — retrieved chunks with their sources.

    Each chunk becomes its own card: a clickable title link to ``source_uri``,
    a meta line (source, page), a relevance progress bar, and a truncated
    content preview. The panel is collapsed by default and the number of
    rendered chunks follows ``len(chunks)`` — the reranker may return 3, 5 or
    8 chunks depending on ``RetrieverConfig`` (ADR-017/ADR-020).

    Args:
        chunks: list of ``{source_uri, title, page, content_preview, score}``
            dicts. Missing fields degrade gracefully: the title falls back to
            ``source_uri`` then ``"Chunk {index}"``, ``page`` is omitted, and
            the score bar renders at 0.0.
    """
    import streamlit as st

    if not chunks:
        return

    with st.expander(f"📚 RAG citations ({len(chunks)} chunks)", expanded=False):
        for index, chunk in enumerate(chunks, 1):
            _render_citation_card(index, chunk)


def _render_citation_card(index: int, chunk: dict[str, Any]) -> None:
    """Render a single citation card: link, meta line, score bar, preview."""
    import streamlit as st

    source_uri = str(chunk.get("source_uri") or "")
    title = str(chunk.get("title") or source_uri or f"Chunk {index}")
    page = chunk.get("page")
    score = _citation_score(chunk.get("score"))

    label = _escape_markdown_label(title)
    if source_uri:
        st.markdown(f"**{index}. [{label}]({source_uri})**")
    else:
        st.markdown(f"**{index}. {label}**")

    meta_parts = [f"📎 {source_uri or 'unknown source'}"]
    if page is not None:
        meta_parts.append(f"📄 p.{page}")
    st.caption(" · ".join(meta_parts))

    st.progress(score, text=f"Relevance: {score:.2f}")

    st.markdown(_citation_preview(chunk.get("content_preview")))

    st.divider()


def _render_rag_citations_fragment(chunks: list[dict[str, Any]]) -> None:
    """Render the citations panel inside ``@st.fragment`` (UI-3 pattern).

    Isolating the panel keeps expanding/collapsing citations from re-running the
    main chat area, so token streaming continues without lag.  The decorator is
    applied lazily to keep this module importable outside a Streamlit session.
    """
    import streamlit as st

    @st.fragment
    def _fragment() -> None:
        render_rag_citations(chunks)

    _fragment()


def render_web_search_results(results: list[dict[str, Any]]) -> None:
    """Render the web search results panel — results from Tavily (G-3).

    Each result becomes a card: a clickable title link to ``url``, a URL
    caption, the snippet text, and an optional relevance score metric.
    The panel is collapsed by default and the number of rendered results
    follows ``len(results)`` — ``web_search`` returns up to
    ``WebSearchArgs.max_results`` items (5 by default, 20 at most).

    Args:
        results: list of ``{title, url, snippet, score?}`` dicts. ``score`` is
            a Tavily relevance score in ``[0, 1]`` and is optional — not every
            result carries one, and the metric is only rendered when it is
            present.
    """
    import streamlit as st

    if not results:
        return

    with st.expander(
        f"\U0001f310 Web search results ({len(results)})",
        expanded=False,
    ):
        for index, result in enumerate(results, 1):
            _render_web_result_card(index, result)


def _render_web_result_card(index: int, result: dict[str, Any]) -> None:
    """Render a single web search result card (G-3).

    Web results are deliberately *not* rendered through
    ``_render_citation_card`` (G-2): they carry no page, no
    ``content_preview``, and their score semantics differ (Tavily relevance
    vs. reranker score), so they get their own local shape.
    """
    import streamlit as st

    title = str(result.get("title") or result.get("url") or f"Result {index}")
    url = str(result.get("url") or "")
    snippet = str(result.get("snippet") or "")
    score = result.get("score")

    label = _escape_markdown_label(title) if url else title
    if url:
        st.markdown(f"**{index}. [{label}]({url})**")
    else:
        st.markdown(f"**{index}. {label}**")
    st.caption(f"\U0001f517 {url}")

    if snippet:
        st.markdown(snippet)

    if score is not None:
        try:
            st.metric("Relevance", f"{float(score):.2f}")
        except (TypeError, ValueError):
            pass

    st.divider()


def _render_web_search_results_fragment(results: list[dict[str, Any]]) -> None:
    """Render the web search results panel inside ``@st.fragment`` (UI-3 pattern).

    Isolating the panel keeps expanding/collapsing results from re-running the
    main chat area, so token streaming continues without lag. The decorator is
    applied lazily to keep this module importable outside a Streamlit session.
    """
    import streamlit as st

    @st.fragment
    def _fragment() -> None:
        render_web_search_results(results)

    _fragment()


def _render_tool_call_fragment(
    tool_name: str,
    args: dict[str, Any],
    status: Literal["running", "done", "error"] = "running",
    result_preview: dict[str, Any] | None = None,
) -> None:
    """Render a collapsible tool-call preview panel (G-1)."""
    import streamlit as st

    # PII truncation for file_export content
    display_args = dict(args)
    if tool_name == "file_export" and "content" in display_args:
        content = str(display_args["content"])
        display_args["content"] = (content[:200] + "...") if len(content) > 200 else content

    # Collapsible panel inside current chat_message
    with st.expander(f"🔧 {tool_name} — {status}", expanded=False):
        st.json(display_args)
        if result_preview is not None:
            st.caption("Result preview")
            st.json(result_preview)
        if status == "running":
            st.spinner("Running...")
        elif status == "done":
            st.success("Done")
        elif status == "error":
            st.error("Failed")


def handle_tool_event(
    event_type: str,
    data: dict[str, Any],
    client: Any,  # UIClient but circular import
    pending_tool_calls: dict[str, dict],
) -> None:
    """Update state and trigger re-render for tool events (G-1).

    Beyond the generic tool-call preview, two branches also render a
    dedicated results panel: ``retrieved_docs`` renders the RAG citations
    panel (G-2) and a ``tool_result`` for ``web_search`` renders the web
    search results panel (G-3).

    Args:
        event_type: "tool_call" | "tool_result" | "retrieved_docs"
        data: SSE event data (Block H-4 contract)
        client: UIClient instance (StreamlitClient)
        pending_tool_calls: dict[tool_call_id, {tool_name, args, status, result_preview}]
                           in st.session_state
    """
    if event_type == "tool_call":
        pending_tool_calls[data["tool_call_id"]] = {
            "tool_name": data["tool_name"],
            "args": data["args"],
            "status": "running",
            "result_preview": None,
        }
        client.render_tool_call(
            tool_name=data["tool_name"],
            args=data["args"],
            status="running",
        )
    elif event_type == "tool_result":
        tc_id = data["tool_call_id"]
        if tc_id in pending_tool_calls:
            pending_tool_calls[tc_id]["status"] = "done"
            pending_tool_calls[tc_id]["result_preview"] = data.get("preview") or {}
            # Kept so the panel can be re-rendered after the stream ends
            # (Streamlit drops the live tree on the next fragment run).
            if data.get("full_results"):
                pending_tool_calls[tc_id]["full_results"] = list(data["full_results"])
            tc = pending_tool_calls[tc_id]
            client.render_tool_call(
                tool_name=tc["tool_name"],
                args=tc["args"],
                status="done",
                result_preview=tc["result_preview"],
            )
            # G-3: web_search results get their own panel, separate from the
            # tool-call preview above (which keeps the snippet_count preview).
            if tc["tool_name"] == "web_search":
                _render_web_search_results_fragment(data.get("full_results") or [])
    elif event_type == "retrieved_docs":
        # For rag_query — extended preview with citations (G-2)
        tc_id = data["tool_call_id"]
        if tc_id in pending_tool_calls:
            pending_tool_calls[tc_id]["status"] = "done"
            pending_tool_calls[tc_id]["result_preview"] = {
                "chunk_count": data.get("chunk_count", 0),
                "top_score": data.get("top_score", 0.0),
                "source_uris": data.get("source_uris", []),
            }
            if data.get("chunks"):
                pending_tool_calls[tc_id]["chunks"] = list(data["chunks"])
            tc = pending_tool_calls[tc_id]
            client.render_tool_call(
                tool_name=tc["tool_name"],
                args=tc["args"],
                status="done",
                result_preview=tc["result_preview"],
            )
            # G-2 additionally renders citations panel:
            _render_rag_citations_fragment(data.get("chunks", []))


def render_tool_calls(pending_tool_calls: dict[str, dict]) -> None:
    """Re-render every recorded tool-call preview and its results panel (G-1..G-3).

    ``handle_tool_event`` renders into the live Streamlit tree, which Streamlit
    discards whenever the enclosing fragment re-runs.  After a stream finishes
    the fragment returns early, so the previews would otherwise disappear.  This
    helper rebuilds the whole set from the recorded ``pending_tool_calls`` state,
    which also keeps the event handlers free of rendering concerns.

    Args:
        pending_tool_calls: mapping produced by ``handle_tool_event`` —
            ``{tool_call_id: {tool_name, args, status, result_preview,
            chunks?, full_results?}}``.
    """
    for entry in pending_tool_calls.values():
        _render_tool_call_fragment(
            entry["tool_name"],
            entry.get("args") or {},
            entry.get("status", "running"),
            entry.get("result_preview"),
        )
        if entry.get("chunks"):
            _render_rag_citations_fragment(list(entry["chunks"]))
        if entry.get("full_results"):
            _render_web_search_results_fragment(list(entry["full_results"]))


__all__ = [
    "CITATION_PREVIEW_CHARS",
    "FAST_ARTIFACT_FORMATS",
    "PII_HIGH_THRESHOLD_ENV",
    "PII_LOW_THRESHOLD_ENV",
    "fetch_artifact_content",
    "get_mime_type",
    "handle_tool_event",
    "render_artifact_buttons",
    "render_error",
    "render_history",
    "render_message",
    "render_pii_badge",
    "render_rag_citations",
    "render_settings_panel",
    "render_status_badge",
    "render_tool_calls",
    "render_web_search_results",
]


def render_settings_panel(session_state: MutableMapping[str, Any]) -> dict:
    """Рендерит settings panel в sidebar (collapsible). Возвращает
    обновлённый dict с настройками для передачи в agent-service.

    Args:
        session_state: текущий ``st.session_state`` (или любой
            MutableMapping — Streamlit отдаёт ``SessionStateProxy``,
            а не ``dict``). Читает предыдущие значения.

    Returns:
        dict с fields:
            - tools_enabled: list[str] — subset of ["web_search",
                "rag_query", "file_export"] (default: all 3).
            - retrieval_strategy: "vector" | "bm25" | "hybrid"
                (default: "hybrid", ADR-020).
            - reranker: "bge" | "cohere" | "none" (default: "bge",
                ADR-017).
            - max_results: int (web_search max_results, default 5,
                range 1-20).
            - top_k: int (rag_query top_k, default 5, range 1-20).
    """
    import streamlit as st

    with st.sidebar.expander("⚙️ Settings", expanded=False):
        # Sub-section: Tools:
        st.markdown("**Tools**")
        tools_enabled = []
        if st.checkbox("Web search (Tavily)", value=True, key="settings_tool_web_search"):
            tools_enabled.append("web_search")
        if st.checkbox("RAG query (documents)", value=True, key="settings_tool_rag_query"):
            tools_enabled.append("rag_query")
        if st.checkbox("File export", value=True, key="settings_tool_file_export"):
            tools_enabled.append("file_export")

        # Sub-section: Retrieval (only relevant if rag_query enabled):
        if "rag_query" in tools_enabled:
            st.markdown("**Retrieval**")
            retrieval_strategy = st.selectbox(
                "Strategy",
                options=["hybrid", "vector", "bm25"],
                index=0,  # ADR-020 default
                key="settings_retrieval_strategy",
                help="hybrid = BM25 + vector (ADR-020 default); "
                "vector = semantic only; bm25 = exact-term only",
            )
            top_k = st.slider(
                "top_k (chunks to return)",
                min_value=1,
                max_value=20,
                value=5,
                step=1,
                key="settings_top_k",
                help="After reranker (ADR-017); 5 is recommended",
            )

            st.markdown("**Reranker**")
            reranker = st.radio(
                "Model",
                options=["bge", "cohere", "none"],
                index=0,  # ADR-017 default
                key="settings_reranker",
                help="bge = local in-process (ADR-017 default); "
                "cohere = external API (optional); "
                "none = disable reranking (A/B baseline)",
            )
        else:
            # Defaults if rag_query disabled:
            retrieval_strategy = "hybrid"
            top_k = 5
            reranker = "bge"

        # Sub-section: Web search (only if web_search enabled):
        if "web_search" in tools_enabled:
            st.markdown("**Web search**")
            max_results = st.slider(
                "max_results",
                min_value=1,
                max_value=20,
                value=5,
                step=1,
                key="settings_max_results",
                help="Tavily API max results per query",
            )
        else:
            max_results = 5

    # Persist in session_state для следующего re-run:
    settings = {
        "tools_enabled": tools_enabled,
        "retrieval_strategy": retrieval_strategy,
        "reranker": reranker,
        "max_results": max_results,
        "top_k": top_k,
    }
    session_state["settings"] = settings
    return settings
