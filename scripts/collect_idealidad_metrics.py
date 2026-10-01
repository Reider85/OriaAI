#!/usr/bin/env python
"""Prometheus exporter for the architecture ideality metric (ROADMAP §18.2, G-2/F-2).

Exposes the raw repository signals collected by
:mod:`llm_client.observability.idealidad` plus Phase 2 control-point gauges
(ALPHA-PROMPTS F-2):

======================  ====================================================
Metric                  Meaning
======================  ====================================================
``llm_client_loc_total``
                        Production LOC (tests/vendor excluded).
``llm_client_adr_count_total``
                        Number of ADR headings in ``ARCHITECT.md``.
``llm_client_capability_count``
                        Capabilities registered across all roadmap phases.
``llm_client_dependency_count``
                        Runtime dependencies declared in ``pyproject.toml``.
``llm_client_capability_markers_total``
                        Capabilities discovered via ``@capability("...")``.
``llm_client_idealidad_ratio{phase}``
                        ``Δcapabilities / Δcomplexity`` per phase.
``llm_client_phase_capabilities_delta{phase}``
                        Capabilities contributed by the phase.
``llm_client_phase_complexity_delta{phase}``
                        New complexity units contributed by the phase.
``llm_client_phase_min_required{phase}``
                        Minimum acceptable ratio at the phase boundary.
``llm_client_ag_extensions_ratio``
                        Phase 2 AG-extensions ideality (2 caps / 1 dep = 2.0).
``llm_client_ui_extensions_ratio``
                        Phase 2 UI-extensions ideality (1 cap / 0 deps = ∞).
``hybrid_recall_improvement_percentage``
                        Latest hybrid A/B exact_term recall improvement.
``hybrid_recall_latency_overhead_percentage``
                        Latest hybrid A/B latency overhead.
``reranker_recall_at_5``
                        Latest reranker A/B recall@5 (labels: arm).
======================  ====================================================

Usage::

    python scripts/collect_idealidad_metrics.py            # serve on :9101
    python scripts/collect_idealidad_metrics.py --once     # print and exit
    python scripts/collect_idealidad_metrics.py --output PATH.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_idealidad_module() -> ModuleType:
    module_path = SRC_ROOT / "llm_client" / "observability" / "idealidad.py"
    spec = importlib.util.spec_from_file_location("llm_client_idealidad", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load ideality module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


idealidad = _load_idealidad_module()
PHASES = idealidad.PHASES
collect_snapshot = idealidad.collect_snapshot
phase_metric = idealidad.phase_metric

from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest,
    start_http_server,
)

DEFAULT_PORT = 9101
ARCHITECT_PATH = REPO_ROOT / "analytics" / "ARCHITECT.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

REGISTRY = CollectorRegistry()

# Phase 2 AG/UI extension control points (ALPHA-PROMPTS F-2, checklist p.25–26).
AG_EXTENSIONS_RATIO = 2.0  # web_search + rag_query / Tavily API
UI_EXTENSIONS_RATIO = 1000.0  # +1 capability / 0 deps — rendered as ∞ on dashboards


def _gauge(name: str, doc: str, *labels: str) -> Gauge:
    return Gauge(name, doc, list(labels), registry=REGISTRY)


LOC_TOTAL = _gauge("llm_client_loc_total", "Production lines of code (tests/vendor excluded).")
ADR_COUNT = _gauge("llm_client_adr_count_total", "Number of ADRs in ARCHITECT.md.")
CAPABILITY_COUNT = _gauge(
    "llm_client_capability_count", "Capabilities registered across all roadmap phases."
)
DEPENDENCY_COUNT = _gauge(
    "llm_client_dependency_count", "Runtime dependencies declared in pyproject.toml."
)
CAPABILITY_MARKERS = _gauge(
    "llm_client_capability_markers_total", "Capabilities discovered via @capability decorators."
)
IDEALIDAD_RATIO = _gauge(
    "llm_client_idealidad_ratio", "Delta capabilities / Delta complexity per phase.", "phase"
)
PHASE_CAP_DELTA = _gauge(
    "llm_client_phase_capabilities_delta", "Capabilities contributed by the phase.", "phase"
)
PHASE_CPLX_DELTA = _gauge(
    "llm_client_phase_complexity_delta", "New complexity units contributed by the phase.", "phase"
)
PHASE_MIN_REQUIRED = _gauge(
    "llm_client_phase_min_required", "Minimum acceptable ideality ratio at phase boundary.", "phase"
)
PHASE_IS_ACTIVE = _gauge(
    "llm_client_phase_is_active", "1 for the currently active roadmap phase, else 0.", "phase"
)
AG_EXTENSIONS_RATIO_GAUGE = _gauge(
    "llm_client_ag_extensions_ratio",
    "Phase 2 AG-extensions ideality ratio (web_search + rag_query / Tavily).",
)
UI_EXTENSIONS_RATIO_GAUGE = _gauge(
    "llm_client_ui_extensions_ratio",
    "Phase 2 UI-extensions ideality ratio (G-1..G-4 / 0 new deps; large value = ∞).",
)
HYBRID_RECALL_IMPROVEMENT = _gauge(
    "hybrid_recall_improvement_percentage",
    "Latest hybrid RAG exact_term recall@5 improvement percentage (A/B).",
)
HYBRID_RECALL_LATENCY_OVERHEAD = _gauge(
    "hybrid_recall_latency_overhead_percentage",
    "Latest hybrid RAG latency overhead percentage vs vector-only (A/B).",
)
HYBRID_RECALL_SUBTYPE_COMPLIANCE = _gauge(
    "hybrid_recall_subtype_compliance",
    "1 when hybrid RAG subtype thresholds are met, else 0.",
    "subtype",
)
RERANKER_RECALL_AT_5 = _gauge("reranker_recall_at_5", "Latest reranker A/B recall@5.", "arm")
RERANKER_FALLBACK_COUNT = _gauge(
    "llm_client_reranker_fallback_count",
    "Reranker chain fallback events from the latest A/B report (0 if no report).",
)

# Last observed A/B values (for --output JSON snapshot).
_last_ab: dict[str, float] = {
    "hybrid_recall_improvement": 0.0,
    "hybrid_recall_latency_overhead": 0.0,
    "reranker_fallback_count": 0.0,
}


def _resolve_root() -> Path:
    return Path(os.getenv("IDEALIDAD_REPO_ROOT", REPO_ROOT)).resolve()


def _latest_json_report(*candidates: Path) -> dict | None:
    """Return the newest JSON report among existing candidate paths."""
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        return None
    newest = max(existing, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _refresh_ab_metrics(root: Path) -> dict[str, float]:
    """Load latest hybrid/reranker A/B reports if present (F-2 Panel 5/7)."""
    hybrid = _latest_json_report(
        root / "test-results" / "hybrid-rag-ab-test" / "report.json",
        root / "test-results" / "hybrid-rag-ab-test" / "latest.json",
        root / "reports" / "hybrid_recall_latest.json",
    )
    reranker = _latest_json_report(
        root / "test-results" / "reranker-ab-test" / "report.json",
        root / "test-results" / "reranker-ab-test" / "latest.json",
        root / "reports" / "reranker_ab_latest.json",
    )

    if hybrid:
        improvement = (
            hybrid.get("improvement", {}).get("recall_improvement_pct")
            or hybrid.get("improvement_pct")
            or hybrid.get("exact_term_improvement_pct")
        )
        if improvement is not None:
            value = float(improvement)
            HYBRID_RECALL_IMPROVEMENT.set(value)
            _last_ab["hybrid_recall_improvement"] = value
        latency = hybrid.get("improvement", {}).get("latency_overhead_pct") or hybrid.get(
            "latency_overhead_pct"
        )
        if latency is not None:
            value = float(latency)
            HYBRID_RECALL_LATENCY_OVERHEAD.set(value)
            _last_ab["hybrid_recall_latency_overhead"] = value
        thresholds = hybrid.get("subtype_thresholds") or hybrid.get("pass_criteria", {}).get(
            "subtype_thresholds"
        )
        if isinstance(thresholds, dict):
            for subtype, ok in thresholds.items():
                HYBRID_RECALL_SUBTYPE_COMPLIANCE.labels(subtype=str(subtype)).set(
                    1.0 if ok else 0.0
                )

    if reranker:
        baseline = reranker.get("baseline", {}).get("recall_at_5")
        treatment = reranker.get("treatment", {}).get("recall_at_5")
        if baseline is not None:
            RERANKER_RECALL_AT_5.labels(arm="baseline").set(float(baseline))
        if treatment is not None:
            RERANKER_RECALL_AT_5.labels(arm="treatment").set(float(treatment))
        fallback = reranker.get("fallback_count")
        if fallback is not None:
            value = float(fallback)
            RERANKER_FALLBACK_COUNT.set(value)
            _last_ab["reranker_fallback_count"] = value

    return dict(_last_ab)


def refresh() -> dict[str, float]:
    """Recompute all signals and update the Prometheus gauges."""
    root = _resolve_root()
    snapshot = collect_snapshot(root, ARCHITECT_PATH, PYPROJECT_PATH)
    active_phase = os.getenv("IDEALIDAD_PHASE", PHASES[0])

    LOC_TOTAL.set(snapshot.loc)
    ADR_COUNT.set(snapshot.adr_count)
    CAPABILITY_COUNT.set(snapshot.capability_count)
    DEPENDENCY_COUNT.set(snapshot.dependency_count)
    CAPABILITY_MARKERS.set(len(snapshot.capability_markers))

    phase2_ratio = 0.0
    for phase in PHASES:
        metric = phase_metric(phase)
        IDEALIDAD_RATIO.labels(phase=phase).set(metric.ratio)
        PHASE_CAP_DELTA.labels(phase=phase).set(metric.capabilities_delta)
        PHASE_CPLX_DELTA.labels(phase=phase).set(metric.complexity_delta)
        PHASE_MIN_REQUIRED.labels(phase=phase).set(metric.min_required)
        PHASE_IS_ACTIVE.labels(phase=phase).set(1 if phase == active_phase else 0)
        if phase == "Phase 2":
            phase2_ratio = metric.ratio

    # Phase 2 AG/UI extension ratios (ALPHA-PROMPTS F-2 hybrid control points).
    AG_EXTENSIONS_RATIO_GAUGE.set(AG_EXTENSIONS_RATIO)
    UI_EXTENSIONS_RATIO_GAUGE.set(UI_EXTENSIONS_RATIO)

    ab = _refresh_ab_metrics(root)

    return {
        "loc": float(snapshot.loc),
        "adr_count": float(snapshot.adr_count),
        "capability_count": float(snapshot.capability_count),
        "dependency_count": float(snapshot.dependency_count),
        "capability_markers": float(len(snapshot.capability_markers)),
        "phase2_adr_ratio": float(phase2_ratio),
        "ag_extensions_ratio": AG_EXTENSIONS_RATIO,
        "ui_extensions_ratio": UI_EXTENSIONS_RATIO,
        **ab,
    }


def _write_output(path: Path, summary: dict[str, float]) -> None:
    """Write a JSON snapshot for CI artefacts (phase2-nightly idealidad job)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary,
        "phases": {},
        "control_points": {
            "phase2_adr_ratio": summary.get("phase2_adr_ratio"),
            "phase2_adr_min_required": phase_metric("Phase 2").min_required,
            "ag_extensions_ratio": AG_EXTENSIONS_RATIO,
            "ui_extensions_ratio": UI_EXTENSIONS_RATIO,
        },
    }
    for phase in PHASES:
        metric = phase_metric(phase)
        payload["phases"][phase] = {
            "capabilities_delta": metric.capabilities_delta,
            "complexity_delta": metric.complexity_delta,
            "ratio": metric.ratio if metric.ratio != float("inf") else "inf",
            "min_required": metric.min_required,
            "passes": metric.passes,
        }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


REFRESH_INTERVAL_SECONDS = 30.0


def _install_scrape_hooks() -> None:
    """Prime all gauges so the first scrape serves values immediately."""
    refresh()


def _refresh_loop() -> None:
    """Keep gauges warm between scrapes (collect_snapshot re-reads the repo)."""
    while True:
        time.sleep(REFRESH_INTERVAL_SECONDS)
        try:
            refresh()
        except Exception as exc:  # noqa: BLE001 - a refresh failure must not kill the exporter
            print(f"Ideality refresh failed: {exc}", file=sys.stderr, flush=True)



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("IDEALIDAD_EXPORTER_PORT", DEFAULT_PORT)),
        help="Port to serve /metrics on (default: %(default)s).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect metrics, print the Prometheus exposition format and exit (used by CI).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write a JSON snapshot of ideality signals to PATH (used by phase2-nightly).",
    )
    args = parser.parse_args(argv)

    if args.once or args.output is not None:
        summary = refresh()
        if args.output is not None:
            _write_output(args.output, summary)
        if args.once:
            sys.stdout.write(generate_latest(REGISTRY).decode())
        if args.output is not None and not args.once:
            print(f"Ideality snapshot written to {args.output}", flush=True)
        return 0

    _install_scrape_hooks()
    threading.Thread(target=_refresh_loop, daemon=True).start()
    start_http_server(args.port, registry=REGISTRY)
    print(f"Ideality metric exporter listening on :{args.port}/metrics", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
