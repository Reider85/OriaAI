#!/usr/bin/env python
"""UI latency benchmark for @st.fragment evaluation (prompt 11).

Measures the effect of Streamlit 1.40+ ``@st.fragment`` (prompts 9-10) on
token streaming performance.  The benchmark:

1. Starts a mock agent-service that emits 1000 tokens at 50 ms intervals.
2. Opens the Streamlit UI via Playwright (Chrome headless).
3. Sends a prompt and periodically samples the chat area's DOM text length.
4. Computes token rendering FPS from text growth rate.
5. Counts sidebar DOM mutations to verify fragment isolation.
6. Compares baseline (fragments disabled) vs. with-fragments mode.
7. Writes ``scripts/ui_latency_report.json``.

Environment variables:

=======================  ======================================================
Variable                 Meaning
=======================  ======================================================
``UI3_ENABLED``          ``"true"`` → fragments ON (prompts 9-10); ``"false"``
                         → baseline, fragments OFF.  Default: ``"false"``.
``UI3_FPS_THRESHOLD``    Minimum ``token_fps_with_fragments / token_fps`` ratio
                         for fragments to be *approved*.  Default: ``1.3``.
``MOCK_PORT``            Port for the mock agent-service.  Default: ``8765``.
``STREAMLIT_PORT``       Port for the Streamlit app.  Default: ``8502``.
=======================  ======================================================

Usage::

    python scripts/ui_latency_benchmark.py                 # single run
    python scripts/ui_latency_benchmark.py --full          # baseline + fragments
    python scripts/ui_latency_benchmark.py --once          # skip report, just run
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
REPORT_PATH = REPO_ROOT / "scripts" / "ui_latency_report.json"

MOCK_PORT = int(os.getenv("MOCK_PORT", "8765"))
STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8502"))
TOKEN_COUNT = int(os.getenv("MOCK_TOKEN_COUNT", "1000"))
TOKEN_DELAY_MS = float(os.getenv("MOCK_TOKEN_DELAY_MS", "50"))
FPS_THRESHOLD = float(os.getenv("UI3_FPS_THRESHOLD", "1.3"))
STREAM_DURATION_S = float(os.getenv("BENCHMARK_STREAM_DURATION", "10"))
SAMPLE_INTERVAL_MS = int(os.getenv("BENCHMARK_SAMPLE_INTERVAL_MS", "100"))


def _find_python() -> str:
    candidates = [
        sys.executable,
        str(Path(sys.prefix) / "python.exe"),
        str(Path(sys.prefix) / "python"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return sys.executable


PYTHON = _find_python()


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_for_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_port_free(port):
            return True
        time.sleep(0.2)
    return False


def _kill_proc(proc: subprocess.Popen[bytes]) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except (OSError, subprocess.SubprocessError):
            pass


def _start_mock_service() -> subprocess.Popen[bytes]:
    cmd = [PYTHON, str(REPO_ROOT / "scripts" / "mock_agent_service.py"),
           "--port", str(MOCK_PORT)]
    env = os.environ.copy()
    env["MOCK_TOKEN_COUNT"] = str(TOKEN_COUNT)
    env["MOCK_TOKEN_DELAY_MS"] = str(TOKEN_DELAY_MS)
    proc = subprocess.Popen(cmd, env=env, cwd=str(REPO_ROOT),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not _wait_for_port(MOCK_PORT, timeout=15):
        raise RuntimeError(f"Mock agent-service did not start on port {MOCK_PORT}")
    return proc


def _start_streamlit(ui3_enabled: bool) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["AGENT_SERVICE_URL"] = f"http://127.0.0.1:{MOCK_PORT}"
    env["APP_PORT"] = str(STREAMLIT_PORT)
    env["UI3_ENABLED"] = "true" if ui3_enabled else "false"
    cmd = [
        PYTHON, "-m", "streamlit", "run",
        str(SRC_ROOT / "llm_client" / "ui" / "app.py"),
        "--server.port", str(STREAMLIT_PORT),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    proc = subprocess.Popen(cmd, env=env, cwd=str(REPO_ROOT),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not _wait_for_port(STREAMLIT_PORT, timeout=30):
        raise RuntimeError(f"Streamlit did not start on port {STREAMLIT_PORT}")
    return proc


def _measure_with_playwright(
    streamlit_port: int,
    stream_duration_s: float = STREAM_DURATION_S,
    sample_interval_ms: int = SAMPLE_INTERVAL_MS,
) -> dict[str, Any]:
    """Measure token streaming performance via DOM text length sampling.

    Periodically samples the total text length in chat messages to compute
    the token rendering rate. Also counts sidebar DOM mutations.
    """
    from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]

    metrics: dict[str, Any] = {
        "token_fps": 0.0,
        "sidebar_rerender_count": 0,
        "chat_rerender_count": 0,
        "total_tokens_received": 0,
        "elapsed_ms": 0.0,
        "first_token_ms": 0.0,
    }

    url = f"http://127.0.0.1:{streamlit_port}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # Navigate and wait for Streamlit to load
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(2)  # let Streamlit fully hydrate

        # Set up sidebar mutation counter
        page.evaluate("""() => {
            window.__bench = { sidebarRenders: 0 };
            const sidebar = document.querySelector('[data-testid="stSidebar"]');
            if (sidebar) {
                const obs = new MutationObserver(() => {
                    window.__bench.sidebarRenders++;
                });
                obs.observe(sidebar, { childList: true, subtree: true });
            }
        }""")

        # Find and fill chat input
        chat_input = page.locator('[data-testid="stChatInput"] textarea')
        if chat_input.count() == 0:
            chat_input = page.locator('textarea').first

        chat_input.click()
        chat_input.fill("Benchmark prompt for latency measurement")
        page.keyboard.press("Enter")

        # Wait for streaming to start and collect samples
        start_time = time.monotonic()
        samples: list[dict[str, float]] = []

        deadline = start_time + stream_duration_s + 5
        while time.monotonic() < deadline:
            # Sample DOM text length
            text_length = page.evaluate("""() => {
                const msgs = document.querySelectorAll('[data-testid="stChatMessage"]');
                let total = 0;
                msgs.forEach(m => total += (m.textContent || '').length);
                return total;
            }""")
            now = time.monotonic()
            samples.append({
                "time_ms": (now - start_time) * 1000,
                "text_length": float(text_length),
            })

            if (now - start_time) >= stream_duration_s:
                break
            time.sleep(sample_interval_ms / 1000.0)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Click sidebar mid-stream to test fragment isolation
        sidebar_button = page.locator('button:has-text("New session")')
        if sidebar_button.count() > 0:
            sidebar_button.first.click()
            time.sleep(1)

        # Get sidebar render count
        bench_data = page.evaluate("""() => {
            return { sidebarRenders: window.__bench.sidebarRenders };
        }""")

        browser.close()

    # Analyze samples
    metrics["sidebar_rerender_count"] = bench_data.get("sidebarRenders", 0)
    metrics["elapsed_ms"] = elapsed_ms

    if len(samples) >= 2:
        # Find the first sample where text appeared (first token)
        for s in samples:
            if s["text_length"] > 0:
                metrics["first_token_ms"] = s["time_ms"]
                break

        # Compute FPS from text growth rate
        # Filter samples where text is growing (streaming active)
        growing_samples = []
        for i in range(1, len(samples)):
            delta_len = samples[i]["text_length"] - samples[i-1]["text_length"]
            if delta_len > 0:
                growing_samples.append({
                    "dt_ms": samples[i]["time_ms"] - samples[i-1]["time_ms"],
                    "dtext": delta_len,
                })

        if growing_samples:
            total_dt = sum(s["dt_ms"] for s in growing_samples)
            total_dtext = sum(s["dtext"] for s in growing_samples)
            # Average token is ~4 characters
            estimated_tokens = total_dtext / 4.0
            metrics["total_tokens_received"] = int(estimated_tokens)
            if total_dt > 0:
                metrics["token_fps"] = (estimated_tokens / total_dt) * 1000.0

    return metrics


def run_single(ui3_enabled: bool, label: str) -> dict[str, Any]:
    """Run one benchmark iteration (mock + streamlit + playwright)."""
    print(f"\n{'='*60}")
    print(f"  Running benchmark: {label} (UI3_ENABLED={ui3_enabled})")
    print(f"{'='*60}")

    mock_proc = _start_mock_service()
    st_proc = None
    try:
        st_proc = _start_streamlit(ui3_enabled)
        time.sleep(2)  # let Streamlit fully start

        metrics = _measure_with_playwright(STREAMLIT_PORT)
        metrics["mode"] = label
        metrics["ui3_enabled"] = ui3_enabled
        metrics["token_count_target"] = TOKEN_COUNT
        metrics["token_delay_ms"] = TOKEN_DELAY_MS

        print(f"  token_fps:          {metrics['token_fps']:.2f}")
        print(f"  sidebar_renders:    {metrics['sidebar_rerender_count']}")
        print(f"  tokens_received:    {metrics['total_tokens_received']}")
        print(f"  elapsed_ms:         {metrics['elapsed_ms']:.0f}")
        print(f"  first_token_ms:     {metrics['first_token_ms']:.0f}")
        return metrics
    finally:
        if st_proc:
            _kill_proc(st_proc)
        _kill_proc(mock_proc)
        time.sleep(1)


def run_full_benchmark() -> dict[str, Any]:
    """Run baseline (fragments OFF) then with-fragments and compare."""
    baseline = run_single(ui3_enabled=False, label="baseline")
    fragments = run_single(ui3_enabled=True, label="with_fragments")

    ratio = (
        fragments["token_fps"] / baseline["token_fps"]
        if baseline["token_fps"] > 0
        else 0.0
    )
    decision = "approved" if ratio >= FPS_THRESHOLD else "rejected"

    report: dict[str, Any] = {
        "baseline": baseline,
        "with_fragments": fragments,
        "ratio": round(ratio, 4),
        "threshold": FPS_THRESHOLD,
        "decision": decision,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n{'='*60}")
    print("  Benchmark Report")
    print(f"{'='*60}")
    print(f"  baseline token_fps:    {baseline['token_fps']:.2f}")
    print(f"  fragments token_fps:   {fragments['token_fps']:.2f}")
    print(f"  ratio:                 {ratio:.4f}")
    print(f"  threshold:             {FPS_THRESHOLD}")
    print(f"  decision:              {decision}")
    print(f"\n  Report saved to: {REPORT_PATH}")

    if decision == "rejected":
        print(f"\n  REJECTED: fragments did not improve FPS by >= {FPS_THRESHOLD*100:.0f}%")
        print("  Per BACKLOG.md §6.2, UI-3 should be rolled back.")
    else:
        print(f"\n  APPROVED: fragments improved FPS by {(ratio-1)*100:.1f}%")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run both baseline and with-fragments, compare, and write report.",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single iteration based on UI3_ENABLED env var.",
    )
    args = parser.parse_args()

    if args.full:
        report = run_full_benchmark()
        return 0 if report["decision"] == "approved" else 1

    if args.once:
        ui3 = os.getenv("UI3_ENABLED", "false").lower() in ("true", "1", "yes")
        label = "with_fragments" if ui3 else "baseline"
        metrics = run_single(ui3_enabled=ui3, label=label)
        REPORT_PATH.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
        return 0

    # Default: single run from env
    ui3 = os.getenv("UI3_ENABLED", "false").lower() in ("true", "1", "yes")
    label = "with_fragments" if ui3 else "baseline"
    metrics = run_single(ui3_enabled=ui3, label=label)
    REPORT_PATH.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
