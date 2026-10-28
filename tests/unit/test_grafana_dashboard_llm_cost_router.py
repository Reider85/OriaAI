"""F-2: Phase 3 control-point Grafana dashboard `llm-cost-router.json`."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_PATH = REPO_ROOT / "ops" / "grafana" / "dashboards" / "Phase 3" / "llm-cost-router.json"
PROVIDER_PATH = REPO_ROOT / "ops" / "grafana" / "provisioning" / "dashboards" / "provider.yml"
ARCHITECTURE_DASHBOARD_DIR = REPO_ROOT / "ops" / "grafana" / "dashboards" / "Architecture"
IDEALIDAD_EXPORTER_PATH = REPO_ROOT / "scripts" / "collect_idealidad_metrics.py"

REQUIRED_PANEL_TITLES = (
    "Router Decisions",
    "Cost Guard",
    "Circuit Breaker",
    "Budget Usage",
    "LLM Calls",
    "Latency",
    "Semantic Cache",
    "Tool Calling Mode",
    "Ideality Metric",
)

ABSOLUTE_RANGE_RE = re.compile(r"\[\d{4}-\d{2}-\d{2}")
RELATIVE_RANGE_RE = re.compile(r"\d+(?:s|m|h|d|w|y)")


def _load_dashboard() -> dict:
    return json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))


def _all_exprs(data: dict) -> list[str]:
    return [
        target.get("expr", "") for panel in data["panels"] for target in panel.get("targets", [])
    ]


class TestDashboardJson:
    def test_dashboard_json_valid(self):
        data = _load_dashboard()
        assert isinstance(data["panels"], list)
        assert data["uid"] == "llm-cost-router"
        assert data["schemaVersion"] >= 30

    def test_dashboard_contains_required_panels(self):
        data = _load_dashboard()
        titles = [panel["title"] for panel in data["panels"]]
        assert len(titles) == 9, f"expected 9 panels, got {len(titles)}"
        joined = " | ".join(titles)
        for needle in REQUIRED_PANEL_TITLES:
            assert needle in joined, f"missing panel covering {needle!r} (have: {titles})"

    def test_panels_have_valid_prometheus_queries(self):
        data = _load_dashboard()
        assert len(data["panels"]) > 0
        for panel in data["panels"]:
            targets = panel.get("targets", [])
            assert targets, f"panel {panel['title']!r} has no targets"
            for target in targets:
                expr = target.get("expr")
                assert isinstance(expr, str) and expr.strip(), (
                    f"panel {panel['title']!r} has empty expr"
                )
                assert target.get("refId"), f"panel {panel['title']!r} target missing refId"
                datasource = target.get("datasource", {})
                assert datasource.get("uid") == "prometheus", (
                    f"panel {panel['title']!r} target must use the provisioned prometheus datasource"
                )


class TestDashboardStructureConventions:
    def test_dashboard_tags_and_refresh(self):
        data = _load_dashboard()
        assert "phase-3" in data["tags"]
        assert data["refresh"] == "30s"
        assert data["timezone"] == "utc"
        assert data["time"] == {"from": "now-1h", "to": "now"}

    def test_panel_ids_unique_and_layout_present(self):
        data = _load_dashboard()
        ids = [panel["id"] for panel in data["panels"]]
        assert sorted(ids) == list(range(1, 10)), f"panel ids must be 1..9, got {ids}"
        for panel in data["panels"]:
            grid = panel.get("gridPos", {})
            for key in ("h", "w", "x", "y"):
                assert isinstance(grid.get(key), int), (
                    f"panel {panel['title']!r} missing gridPos.{key}"
                )
                assert grid[key] >= 0, f"panel {panel['title']!r} gridPos.{key} must be >= 0"
            assert grid["h"] > 0 and grid["w"] > 0, (
                f"panel {panel['title']!r} must have positive size"
            )

    def test_exprs_use_only_relative_time_ranges(self):
        for expr in _all_exprs(_load_dashboard()):
            assert not ABSOLUTE_RANGE_RE.search(expr), f"absolute time range in expr: {expr}"
            for match in re.finditer(r"\[([^\]]+)\]", expr):
                window = match.group(1)
                assert RELATIVE_RANGE_RE.fullmatch(window), (
                    f"non-relative range [{window}] in expr: {expr}"
                )

    def test_ideality_panel_uses_real_metric_not_hardcoded_constant(self):
        data = _load_dashboard()
        ideality = next(p for p in data["panels"] if "Ideality Metric" in p["title"])
        exprs = " ".join(target.get("expr", "") for target in ideality.get("targets", []))
        assert 'llm_client_idealidad_ratio{phase="Phase 3"}' in exprs
        assert exprs.strip() != "4/2", "ideality must read the exporter metric, not a constant"


class TestMetricNamesMatchModule:
    def test_dashboard_metrics_exposed_by_llm_metrics_registry(self):
        from prometheus_client import generate_latest

        from llm_client.observability import llm_metrics

        llm_metrics.record_llm_call(
            provider="openai",
            model="gpt-4o-mini",
            status="success",
            mode="native",
            latency_seconds=0.5,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.001,
        )
        llm_metrics.record_router_decision(
            provider="openai",
            model="gpt-4o-mini",
            policy="cost",
            reason="cheapest",
            circuit_breaker_active=False,
        )
        llm_metrics.record_cache_hit("hit")
        llm_metrics.update_budget_usage(80.0, 100.0)

        exposition = generate_latest(llm_metrics.REGISTRY).decode()
        for metric in (
            "llm_call_total",
            "llm_call_latency_seconds",
            "llm_monthly_budget_usage_ratio",
            "semantic_cache_hits_total",
            "router_decisions_total",
        ):
            assert metric in exposition, f"{metric} missing from REGISTRY exposition"
            assert metric in " ".join(_all_exprs(_load_dashboard())), (
                f"dashboard does not reference {metric}"
            )

    def test_ideality_exporter_declares_phase3_ratio_metric(self):
        source = IDEALIDAD_EXPORTER_PATH.read_text(encoding="utf-8")
        assert "llm_client_idealidad_ratio" in source
        assert "phase_metric = idealidad.phase_metric" in source

    def test_phase3_control_point_ratio_is_2_0(self):
        from llm_client.observability.idealidad import phase_metric

        metric = phase_metric("Phase 3")
        assert metric.capabilities_delta == 4
        assert metric.complexity_delta == 2
        assert metric.ratio == 2.0
        assert metric.passes, "Phase 3 control point 4/2 = 2.0 must pass (≥1.5)"


class TestProvisioning:
    def test_phase3_folder_contains_dashboard(self):
        assert DASHBOARD_PATH.is_file(), f"missing dashboard at {DASHBOARD_PATH}"
        assert DASHBOARD_PATH.parent.name == "Phase 3"

    def test_phase12_dashboards_preserved_in_architecture_folder(self):
        for name in (
            "idealidad.json",
            "checkpoint-latency.json",
            "checkpoint-recovery.json",
            "hybrid-recall.json",
        ):
            assert (ARCHITECTURE_DASHBOARD_DIR / name).is_file(), (
                f"Phase 1/2 dashboard {name} must stay in Architecture folder"
            )

    def test_provider_yml_uses_file_structure_folders(self):
        content = PROVIDER_PATH.read_text(encoding="utf-8")
        assert "foldersFromFilesStructure: true" in content
        assert "path: /var/lib/grafana/dashboards" in content
        assert "folder:" not in content, "explicit folder would override structure-based folders"
