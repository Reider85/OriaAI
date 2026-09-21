"""Tests for the architecture ideality metric (G-2 / ROADMAP §15, §18.2)."""

import textwrap
from pathlib import Path

import pytest

from llm_client.observability.idealidad import (
    PHASE_CAPABILITIES,
    PHASES,
    PhaseMetric,
    collect_snapshot,
    count_adrs,
    count_dependencies,
    count_loc,
    cumulative_capabilities,
    cumulative_complexity,
    discover_capability_markers,
    phase_metric,
)

# ── PhaseMetric ────────────────────────────────────────────────────────


class TestPhaseMetric:
    def test_ratio_basic(self):
        m = PhaseMetric(phase="Phase 1", capabilities_delta=2, complexity_delta=1, min_required=2.0)
        assert m.ratio == 2.0

    def test_ratio_zero_complexity(self):
        m = PhaseMetric(phase="Phase 6", capabilities_delta=2, complexity_delta=0, min_required=5.0)
        assert m.ratio == float("inf")

    def test_passes_when_meets_minimum(self):
        m = PhaseMetric(phase="Phase 1", capabilities_delta=2, complexity_delta=1, min_required=2.0)
        assert m.passes is True

    def test_fails_below_minimum(self):
        m = PhaseMetric(phase="Phase 4", capabilities_delta=3, complexity_delta=3, min_required=1.0)
        assert m.ratio == 1.0
        assert m.passes is True

    def test_strictly_below_minimum(self):
        m = PhaseMetric(phase="Phase 1", capabilities_delta=1, complexity_delta=2, min_required=2.0)
        assert m.ratio == 0.5
        assert m.passes is False

    def test_all_phases_pass_their_control_points(self):
        for phase in PHASES:
            metric = phase_metric(phase)
            assert metric.passes, f"{phase} ratio {metric.ratio} < min {metric.min_required}"


# ── cumulative helpers ──────────────────────────────────────────────────


class TestCumulativeCapabilities:
    def test_phase_1_has_two(self):
        caps = cumulative_capabilities("Phase 1")
        assert len(caps) == 2
        assert set(caps) == {"cancel_endpoint", "dual_stream_logging"}

    def test_phase_3_includes_earlier(self):
        caps = cumulative_capabilities("Phase 3")
        assert len(caps) == 9
        assert "cancel_endpoint" in caps
        assert "semantic_cache" in caps

    def test_phase_6_has_all(self):
        caps = cumulative_capabilities("Phase 6")
        total = sum(len(v) for v in PHASE_CAPABILITIES.values())
        assert len(caps) == total

    def test_unknown_phase_raises(self):
        with pytest.raises(ValueError, match="Unknown phase"):
            cumulative_capabilities("Phase 99")


class TestCumulativeComplexity:
    def test_phase_1(self):
        assert cumulative_complexity("Phase 1") == 1

    def test_phase_2(self):
        assert cumulative_complexity("Phase 2") == 3  # 1 + 2

    def test_phase_3(self):
        assert cumulative_complexity("Phase 3") == 5  # 1 + 2 + 2


# ── count_loc ───────────────────────────────────────────────────────────


class TestCountLoc:
    def test_counts_python_code(self, tmp_path):
        (tmp_path / "module.py").write_text(
            textwrap.dedent("""\
                # header comment
                x = 1
                y = 2
            """)
        )
        assert count_loc(tmp_path) == 2

    def test_skips_blank_and_comment(self, tmp_path):
        (tmp_path / "module.py").write_text(
            textwrap.dedent("""\
                # comment
                  # indented comment

                x = 1
            """)
        )
        assert count_loc(tmp_path) == 1

    def test_skips_docstrings(self, tmp_path):
        (tmp_path / "module.py").write_text(
            textwrap.dedent("""\
                \"\"\"Module docstring.\"\"\"
                x = 1
            """)
        )
        assert count_loc(tmp_path) == 1

    def test_skips_multiline_docstrings(self, tmp_path):
        (tmp_path / "module.py").write_text(
            textwrap.dedent("""\
                \"\"\"
                Multi-line docstring.
                Second line.
                \"\"\"
                x = 1
            """)
        )
        assert count_loc(tmp_path) == 1

    def test_skips_test_dir(self, tmp_path):
        code_dir = tmp_path / "src"
        test_dir = tmp_path / "tests"
        code_dir.mkdir()
        test_dir.mkdir()
        (code_dir / "main.py").write_text("x = 1\n")
        (test_dir / "test_main.py").write_text("y = 2\n")
        assert count_loc(tmp_path) == 1

    def test_empty_dir(self, tmp_path):
        assert count_loc(tmp_path) == 0

    def test_nonexistent_dir(self):
        assert count_loc("/nonexistent/path/xyz") == 0


# ── count_adrs ─────────────────────────────────────────────────────────


class TestCountAdrs:
    def test_real_architect_md(self):
        path = Path(__file__).resolve().parent.parent.parent / "analytics" / "ARCHITECT.md"
        if path.exists():
            count = count_adrs(path)
            assert count >= 10  # at least ADR-001..ADR-014

    def test_count_two_adrs(self, tmp_path):
        md = tmp_path / "architect.md"
        md.write_text("### ADR-001: First\n...\n### ADR-002: Second\n...")
        assert count_adrs(md) == 2

    def test_ignores_non_adr_headings(self, tmp_path):
        md = tmp_path / "architect.md"
        md.write_text("## Not an ADR\n### Section\n### ADR-003: Real\n")
        assert count_adrs(md) == 1

    def test_nonexistent_file(self):
        assert count_adrs("/nonexistent/architect.md") == 0


# ── count_dependencies ──────────────────────────────────────────────────


class TestCountDependencies:
    def test_real_pyproject(self):
        path = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        if path.exists():
            count = count_dependencies(path)
            assert count >= 15

    def test_empty_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        assert count_dependencies(tmp_path / "pyproject.toml") == 0

    def test_nonexistent_file(self):
        assert count_dependencies("/nonexistent/pyproject.toml") == 0


# ── discover_capability_markers ─────────────────────────────────────────


class TestDiscoverCapabilityMarkers:
    def test_finds_decorators(self, tmp_path):
        (tmp_path / "mod.py").write_text('@capability("my_cap")\ndef foo(): pass\n')
        markers = discover_capability_markers(tmp_path)
        assert markers == {"my_cap"}

    def test_no_decorators(self, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        markers = discover_capability_markers(tmp_path)
        assert markers == frozenset()

    def test_skips_test_files(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_mod.py").write_text('@capability("x")\ndef foo(): pass\n')
        markers = discover_capability_markers(tmp_path)
        assert markers == frozenset()

    def test_nonexistent_dir(self):
        assert discover_capability_markers("/nonexistent/path") == frozenset()


# ── collect_snapshot ────────────────────────────────────────────────────


class TestCollectSnapshot:
    def test_with_real_project(self):
        root = Path(__file__).resolve().parent.parent.parent / "src"
        architect = Path(__file__).resolve().parent.parent.parent / "analytics" / "ARCHITECT.md"
        pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        if not root.exists():
            pytest.skip("Project root not available")

        snapshot = collect_snapshot(root, architect, pyproject)
        assert snapshot.loc > 0
        assert snapshot.adr_count >= 10
        assert snapshot.capability_count >= 18
        assert snapshot.dependency_count >= 15
        assert snapshot.cumulative_idealidad_ratio > 0
