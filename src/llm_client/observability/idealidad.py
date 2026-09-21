"""Ideality metric — ``Δfunctionality / Δcomplexity`` (ROADMAP §15).

The ideality ratio measures how much *functionality* each unit of *complexity*
buys, protecting the project from "false maturity" (see ROADMAP §15.1). For every
new ADR the control inequality is ``Δфункциональности / Δсложности >= 1``.

This module is the single source of truth for:

* the per-phase capability / complexity deltas (ROADMAP §5.6, §6.6, §7.6, ...);
* the phase control points (ROADMAP §15.2);
* automatic extraction of the raw signals — LOC, ADR count, dependency count and
  capability markers (ROADMAP §15.3).

The Prometheus exporter in ``scripts/collect_idealidad_metrics.py`` consumes the
:func:`collect_snapshot` / :func:`phase_metric` helpers.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

PHASES: tuple[str, ...] = (
    "Phase 1",
    "Phase 2",
    "Phase 3",
    "Phase 4",
    "Phase 5",
    "Phase 6",
)

#: Capabilities introduced by each phase (ROADMAP control points §5.6, §6.6, ...).
PHASE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "Phase 1": ("cancel_endpoint", "dual_stream_logging"),
    "Phase 2": ("async_checkpoint", "reranker", "hybrid_retrieval"),
    "Phase 3": (
        "semantic_cache",
        "cost_aware_router",
        "tool_capability_adapter",
        "mcp_server_preview",
    ),
    "Phase 4": ("plugin_registry", "transport_auto_negotiation", "cycle_detection"),
    "Phase 5": ("multi_instance", "mcp_security", "async_rendering", "granular_access"),
    "Phase 6": ("mcp_server_full", "embed_mode"),
}

#: New complexity units (dependencies / abstractions) added per phase (ROADMAP §15.2).
PHASE_NEW_COMPLEXITY: dict[str, int] = {
    "Phase 1": 1,  # KMS / Vault
    "Phase 2": 2,  # bge-reranker, tsvector
    "Phase 3": 2,  # net: +3 abstractions, -1 (fallback_chain упразднён)
    "Phase 4": 3,  # VectorStoreRegistry, MCPTransport, state-delta detector
    "Phase 5": 4,  # Redis SessionStore, Vault, Worker, Auth provider
    "Phase 6": 0,  # надсистема без роста сложности
}

#: Minimum acceptable ``Δф/Δсложности`` at the end of each phase (ROADMAP §15.2).
PHASE_MIN_IDEALIDAD: dict[str, float] = {
    "Phase 1": 2.0,
    "Phase 2": 1.5,
    "Phase 3": 1.5,
    "Phase 4": 1.0,
    "Phase 5": 1.0,
    "Phase 6": 5.0,
}

#: Directories excluded from the LOC signal — production code only (ROADMAP §15.3).
DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "tests",
        "test",
        "vendor",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "build",
        "dist",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

_ADR_RE = re.compile(r"^#{2,3}\s+ADR-\d+", re.MULTILINE)
_CAPABILITY_RE = re.compile(r"@capability\(\s*[\"']([^\"']+)[\"']\s*\)")


@dataclass(frozen=True)
class PhaseMetric:
    """Ideality delta for a single phase."""

    phase: str
    capabilities_delta: int
    complexity_delta: int
    min_required: float

    @property
    def ratio(self) -> float:
        """``Δcapabilities / Δcomplexity`` — ``inf`` when no new complexity."""
        if self.complexity_delta == 0:
            return float("inf")
        return self.capabilities_delta / self.complexity_delta

    @property
    def passes(self) -> bool:
        """True when the phase control point is satisfied."""
        return self.ratio >= self.min_required


@dataclass(frozen=True)
class IdealitySnapshot:
    """Raw signals extracted from the repository (ROADMAP §15.3)."""

    loc: int
    adr_count: int
    capability_count: int
    dependency_count: int
    capability_markers: frozenset[str]

    @property
    def cumulative_idealidad_ratio(self) -> float:
        """Overall ``Σcapabilities / Σnew complexity`` across the roadmap."""
        total_complexity = sum(PHASE_NEW_COMPLEXITY.values())
        if total_complexity == 0:
            return float("inf")
        return len(_all_capabilities()) / total_complexity


def _all_capabilities() -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for phase in PHASES:
        for capability in PHASE_CAPABILITIES[phase]:
            seen.setdefault(capability, None)
    return tuple(seen)


def count_loc(root: str | Path, *, excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS) -> int:
    """Count non-blank, non-comment Python source lines under ``root``.

    Test and vendor directories are skipped so the metric reflects production
    code only (ROADMAP §15.3 anti-pattern).
    """
    base = Path(root)
    if not base.exists():
        return 0

    total = 0
    for path in base.rglob("*.py"):
        if any(part in excluded_dirs for part in path.relative_to(base).parts[:-1]):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total += _count_code_lines(content)
    return total


def _count_code_lines(content: str) -> int:
    """Count non-blank, non-comment, non-docstring lines in a Python module."""
    count = 0
    delimiter: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if delimiter is not None:
            if delimiter in line:
                delimiter = None
            continue
        if line.startswith("#"):
            continue
        for quote in ('"""', "'''"):
            if line.startswith(quote):
                if line.count(quote) < 2:
                    delimiter = quote
                break
        else:
            count += 1
    return count


def count_adrs(architect_path: str | Path) -> int:
    """Count ADR headings in ``ARCHITECT.md`` (``## ADR-NNN`` / ``### ADR-NNN``)."""
    path = Path(architect_path)
    if not path.exists():
        return 0
    return len(_ADR_RE.findall(path.read_text(encoding="utf-8")))


def count_dependencies(pyproject_path: str | Path) -> int:
    """Count runtime dependencies declared under ``[project].dependencies``."""
    path = Path(pyproject_path)
    if not path.exists():
        return 0
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return len(data.get("project", {}).get("dependencies", []))


def discover_capability_markers(root: str | Path) -> frozenset[str]:
    """Find capabilities declared via ``@capability("name")`` decorators."""
    base = Path(root)
    if not base.exists():
        return frozenset()

    found: set[str] = set()
    for path in base.rglob("*.py"):
        rel_parts = path.relative_to(base).parts
        if any(part.startswith(("test", "vendor")) for part in rel_parts[:-1]):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found.update(_CAPABILITY_RE.findall(content))
    return frozenset(found)


def cumulative_capabilities(phase: str) -> tuple[str, ...]:
    """All capabilities available up to and including ``phase``."""
    if phase not in PHASE_CAPABILITIES:
        raise ValueError(f"Unknown phase {phase!r}; expected one of {PHASES}")

    seen: dict[str, None] = {}
    for candidate in PHASES:
        for capability in PHASE_CAPABILITIES[candidate]:
            seen.setdefault(capability, None)
        if candidate == phase:
            break
    return tuple(seen)


def cumulative_complexity(phase: str) -> int:
    """Sum of new complexity units up to and including ``phase``."""
    if phase not in PHASE_NEW_COMPLEXITY:
        raise ValueError(f"Unknown phase {phase!r}; expected one of {PHASES}")
    upto = PHASES.index(phase)
    return sum(PHASE_NEW_COMPLEXITY[candidate] for candidate in PHASES[: upto + 1])


def phase_metric(phase: str) -> PhaseMetric:
    """Per-phase ideality delta plus its control-point requirement."""
    if phase not in PHASE_CAPABILITIES:
        raise ValueError(f"Unknown phase {phase!r}; expected one of {PHASES}")
    return PhaseMetric(
        phase=phase,
        capabilities_delta=len(PHASE_CAPABILITIES[phase]),
        complexity_delta=PHASE_NEW_COMPLEXITY[phase],
        min_required=PHASE_MIN_IDEALIDAD[phase],
    )


def collect_snapshot(
    root: str | Path,
    architect_path: str | Path,
    pyproject_path: str | Path,
) -> IdealitySnapshot:
    """Extract all raw ideality signals from the repository."""
    markers = discover_capability_markers(root)
    return IdealitySnapshot(
        loc=count_loc(root),
        adr_count=count_adrs(architect_path),
        capability_count=len(_all_capabilities()),
        dependency_count=count_dependencies(pyproject_path),
        capability_markers=markers,
    )


__all__ = [
    "DEFAULT_EXCLUDED_DIRS",
    "PHASES",
    "PHASE_CAPABILITIES",
    "PHASE_MIN_IDEALIDAD",
    "PHASE_NEW_COMPLEXITY",
    "IdealitySnapshot",
    "PhaseMetric",
    "collect_snapshot",
    "count_adrs",
    "count_dependencies",
    "count_loc",
    "cumulative_capabilities",
    "cumulative_complexity",
    "discover_capability_markers",
    "phase_metric",
]
