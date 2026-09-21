#!/usr/bin/env python
"""Prometheus exporter for the architecture ideality metric (ROADMAP §18.2, G-2).

Exposes the raw repository signals collected by
:mod:`llm_client.observability.idealidad`:

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
======================  ====================================================

Usage::

    python scripts/collect_idealidad_metrics.py            # serve on :9101
    python scripts/collect_idealidad_metrics.py --once     # print and exit
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest,
    start_http_server,
)

from llm_client.observability.idealidad import (
    PHASES,
    collect_snapshot,
    phase_metric,
)

DEFAULT_PORT = 9101
ARCHITECT_PATH = REPO_ROOT / "analytics" / "ARCHITECT.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

REGISTRY = CollectorRegistry()


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

_GAUGES = (
    LOC_TOTAL,
    ADR_COUNT,
    CAPABILITY_COUNT,
    DEPENDENCY_COUNT,
    CAPABILITY_MARKERS,
    IDEALIDAD_RATIO,
    PHASE_CAP_DELTA,
    PHASE_CPLX_DELTA,
    PHASE_MIN_REQUIRED,
    PHASE_IS_ACTIVE,
)


def _resolve_root() -> Path:
    return Path(os.getenv("IDEALIDAD_REPO_ROOT", REPO_ROOT)).resolve()


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

    for phase in PHASES:
        metric = phase_metric(phase)
        IDEALIDAD_RATIO.labels(phase=phase).set(metric.ratio)
        PHASE_CAP_DELTA.labels(phase=phase).set(metric.capabilities_delta)
        PHASE_CPLX_DELTA.labels(phase=phase).set(metric.complexity_delta)
        PHASE_MIN_REQUIRED.labels(phase=phase).set(metric.min_required)
        PHASE_IS_ACTIVE.labels(phase=phase).set(1 if phase == active_phase else 0)

    return {
        "loc": float(snapshot.loc),
        "adr_count": float(snapshot.adr_count),
        "capability_count": float(snapshot.capability_count),
        "dependency_count": float(snapshot.dependency_count),
        "capability_markers": float(len(snapshot.capability_markers)),
    }


def _install_scrape_hooks() -> None:
    """Recompute signals lazily on every Prometheus scrape."""
    for gauge in _GAUGES:
        gauge.set_function(refresh)


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
    args = parser.parse_args(argv)

    if args.once:
        refresh()
        sys.stdout.write(generate_latest(REGISTRY).decode())
        return 0

    _install_scrape_hooks()
    start_http_server(args.port, registry=REGISTRY)
    print(f"Ideality metric exporter listening on :{args.port}/metrics", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
