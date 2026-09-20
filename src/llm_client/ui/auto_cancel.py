"""UI watcher for ADR-013 (C-5): auto-cancel LLM sessions on tab close / visibility loss.

Injects a small JavaScript fragment (via ``st.components.v1.html``) into a Streamlit
app that:

  * listens to ``visibilitychange``, ``pagehide`` and ``beforeunload``;
  * debounces ``visibilitychange`` by 5 s so quick tab switches do not spam cancel;
  * ships the cancel via ``navigator.sendBeacon`` (fallback ``fetch keepalive=true``)
    so it survives tab close;
  * exposes a manual ``stop_session()`` JS helper for the "Stop" button.

The backend URL defaults to ``window.location.origin`` and can be overridden with
``backend_origin``.
"""
AUTO_CANCEL_JS = """<script>
(function () {
  "use strict";
  const BACKEND = {{BACKEND_ORIGIN}};
  const DEBOUNCE_MS = 5000;
  let hiddenSince = null;
  let timer = null;

  function sessionIdFromLocation() {
    const params = new URLSearchParams(window.location.search);
    const sid = params.get("session_id") || localStorage.getItem("llm_session_id");
    return sid;
  }

  function sendCancel(reason) {
    const sid = sessionIdFromLocation();
    if (!sid) {
      console.debug("[auto-cancel] no active session, skipping");
      return;
    }
    const url = BACKEND + "/sessions/" + encodeURIComponent(sid) + "/cancel";
    const body = JSON.stringify({ reason: reason });
    const headers = { "Content-Type": "application/json" };
    if (navigator.sendBeacon) {
      const ok = navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
      if (!ok) {
        console.debug("[auto-cancel] sendBeacon failed, falling back to fetch+keepalive");
      } else {
        return;
      }
    }
    fetch(url, { method: "POST", body: body, headers: headers, keepalive: true })
      .catch(function (e) { console.debug("[auto-cancel] fetch error", e); });
  }

  function onVisibility() {
    if (document.hidden) {
      hiddenSince = Date.now();
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        console.debug("[auto-cancel] event=visibilitychange (hidden >5s)");
        sendCancel("tab_closed");
      }, DEBOUNCE_MS);
    } else {
      hiddenSince = null;
      if (timer) { window.clearTimeout(timer); timer = null; }
    }
  }

  function onPageHide() {
    console.debug("[auto-cancel] event=pagehide");
    sendCancel("tab_closed");
  }

  function onBeforeUnload() {
    console.debug("[auto-cancel] event=beforeunload");
    sendCancel("tab_closed");
  }

  document.addEventListener("visibilitychange", onVisibility, false);
  window.addEventListener("pagehide", onPageHide, false);
  window.addEventListener("beforeunload", onBeforeUnload, false);

  window.stop_llm_session = function (reason) {
    reason = reason || "user_cancelled";
    console.debug("[auto-cancel] manual stop, event=button, reason=" + reason);
    sendCancel(reason);
  };
})();
</script>
"""


def inject_auto_cancel(backend_origin: str | None = None) -> None:
    """Render the auto-cancel JS fragment into the current Streamlit page.

    Call from the top of the Streamlit chat script. ``backend_origin`` overrides
    ``window.location.origin`` (useful when the API lives on another port).
    """
    try:
        import streamlit.components.v1 as components  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("streamlit is required for inject_auto_cancel()") from exc

    origin = backend_origin or "window.location.origin"
    js = AUTO_CANCEL_JS.replace("{{BACKEND_ORIGIN}}", _quote(origin))
    components.html(js, height=0, width=0)


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


__all__ = ["AUTO_CANCEL_JS", "inject_auto_cancel"]