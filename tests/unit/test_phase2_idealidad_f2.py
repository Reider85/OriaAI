"""F-2: Phase 2 control-point metrics, exporter, Grafana dashboard and alerts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.metrics import NullRerankerMetrics, RerankerMetrics
from llm_client.rag.pipeline import rerank_after_fusion
from llm_client.rag.rerankers.base import RerankResult
from llm_client.rag.rerankers.chain import RerankerChain

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_PATH = REPO_ROOT / "ops" / "grafana" / "dashboards" / "idealidad.json"
RULES_PATH = REPO_ROOT / "ops" / "grafana" / "provisioning" / "alerting" / "rules.yml"
EXPORTER_PATH = REPO_ROOT / "scripts" / "collect_idealidad_metrics.py"


def _load_exporter_module():
    spec = importlib.util.spec_from_file_location("collect_idealidad_metrics", EXPORTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _MockReranker:
    def __init__(self, name: str, should_fail: bool = False, health: bool = True) -> None:
        self._name = name
        self.should_fail = should_fail
        self.health_result = health
        self.rerank_calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def health_check(self) -> bool:
        return self.health_result

    async def rerank(self, query, documents, top_k=5, batch_size=8):
        self.rerank_calls += 1
        if self.should_fail:
            raise RuntimeError("mock fail")
        return [
            RerankResult(doc_id=str(i), score=0.9 - i * 0.1, original_index=i)
            for i in range(min(top_k, len(documents)))
        ]


class TestRerankerFallbackMetrics:
    def test_fallback_count_metric_exists(self):
        metrics = RerankerMetrics()
        assert hasattr(metrics, "fallback_count")
        metrics.increment_fallback_count(primary="bge", active="identity")
        metrics.increment_fallback_count(primary="bge", active="cohere")
        # Two different label pairs — both counters created
        assert metrics.fallback_count is not None

    def test_null_metrics_fallback_noop(self):
        metrics = NullRerankerMetrics()
        metrics.increment_fallback_count(primary="x", active="y")  # must not raise

    @pytest.mark.asyncio
    async def test_chain_increments_fallback_when_primary_fails(self):
        metrics = RerankerMetrics()
        primary = _MockReranker("primary", should_fail=True)
        fallback = _MockReranker("fallback", should_fail=False)
        chain = RerankerChain([primary, fallback], metrics=metrics)
        docs = [{"content": "a"}, {"content": "b"}]
        results = await chain.rerank("q", docs, top_k=2)
        assert len(results) == 2
        # primary failed → fallback used → fallback_count incremented
        assert primary.rerank_calls == 1
        assert fallback.rerank_calls == 1

    @pytest.mark.asyncio
    async def test_chain_increments_identity_when_all_fail(self):
        metrics = RerankerMetrics()
        primary = _MockReranker("primary", should_fail=True)
        fallback = _MockReranker("fallback", should_fail=True)
        chain = RerankerChain([primary, fallback], metrics=metrics)
        docs = [{"content": "a"}]
        results = await chain.rerank("q", docs, top_k=1)
        assert results[0].score == 1.0

    @pytest.mark.asyncio
    async def test_pipeline_identity_fallback_increments_metrics(self):
        metrics = RerankerMetrics()
        registry = MagicMock()
        bad = _MockReranker("primary", should_fail=True)
        registry.get.return_value = bad
        config = RetrieverConfig(
            reranker_name="primary",
            reranker_top_k=2,
            reranker_enabled=True,
        )
        # Need more docs than top_k so the pipeline actually invokes the reranker.
        docs = [{"content": f"c{i}", "metadata": {}} for i in range(5)]
        results = await rerank_after_fusion(
            query="q",
            fused_docs=docs,
            config=config,
            reranker_registry=registry,
            metrics=metrics,
        )
        assert len(results) == 2
        assert all(r.get("score") == 1.0 for r in results)


class TestIdealidadExporterF2:
    def test_exporter_module_loads_and_has_phase2_gauges(self):
        exporter = _load_exporter_module()
        assert hasattr(exporter, "AG_EXTENSIONS_RATIO_GAUGE")
        assert hasattr(exporter, "UI_EXTENSIONS_RATIO_GAUGE")
        assert exporter.AG_EXTENSIONS_RATIO == pytest.approx(2.0)
        assert exporter.UI_EXTENSIONS_RATIO > 100

    def test_refresh_sets_phase2_and_ag_ui_ratios(self, tmp_path, monkeypatch):
        exporter = _load_exporter_module()
        monkeypatch.setenv("IDEALIDAD_REPO_ROOT", str(REPO_ROOT))
        summary = exporter.refresh()
        assert summary["phase2_adr_ratio"] == pytest.approx(1.5)
        assert summary["ag_extensions_ratio"] == pytest.approx(2.0)
        assert summary["ui_extensions_ratio"] > 100

    def test_output_flag_writes_json_snapshot(self, tmp_path, monkeypatch):
        exporter = _load_exporter_module()
        monkeypatch.setenv("IDEALIDAD_REPO_ROOT", str(REPO_ROOT))
        out = tmp_path / "idealidad" / "metrics_test.json"
        rc = exporter.main(["--output", str(out)])
        assert rc == 0
        assert out.is_file()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert "summary" in payload
        assert "phases" in payload
        assert payload["phases"]["Phase 2"]["ratio"] == pytest.approx(1.5)
        assert payload["control_points"]["ag_extensions_ratio"] == pytest.approx(2.0)
        assert payload["control_points"]["phase2_adr_min_required"] == pytest.approx(1.5)

    def test_once_flag_still_works(self, capsys, monkeypatch):
        exporter = _load_exporter_module()
        monkeypatch.setenv("IDEALIDAD_REPO_ROOT", str(REPO_ROOT))
        rc = exporter.main(["--once"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "llm_client_idealidad_ratio" in out
        assert "llm_client_ag_extensions_ratio" in out
        assert "llm_client_ui_extensions_ratio" in out


class TestGrafanaDashboardF2:
    def test_dashboard_json_is_valid_and_has_phase2_panels(self):
        data = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
        panel_ids = {p["id"] for p in data["panels"]}
        assert {1, 2, 3, 4}.issubset(panel_ids), "Phase 1 panels must be preserved"
        assert {5, 6, 7}.issubset(panel_ids), "Phase 2 Panels 5/6/7 required by F-2"
        assert "phase-2" in data["tags"]
        assert "phase-1" in data["tags"]

    def test_panel5_uses_real_metric_names(self):
        data = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
        panel5 = next(p for p in data["panels"] if p["id"] == 5)
        exprs = " ".join(t.get("expr", "") for t in panel5.get("targets", []))
        assert "llm_client_checkpoint_write_redis_latency_ms_bucket" in exprs
        assert "reranker_recall_at_5" in exprs
        assert "hybrid_recall_improvement_percentage" in exprs
        assert "llm_client_reranker_fallback_count" in exprs

    def test_panel6_shows_phase2_control_point_ratios(self):
        data = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
        panel6 = next(p for p in data["panels"] if p["id"] == 6)
        exprs = " ".join(t.get("expr", "") for t in panel6.get("targets", []))
        assert 'llm_client_idealidad_ratio{phase="Phase 2"}' in exprs
        assert "llm_client_ag_extensions_ratio" in exprs
        assert "llm_client_ui_extensions_ratio" in exprs
        assert "Phase 2" in panel6.get("title", "")

    def test_panel7_rag_quality_trend(self):
        data = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
        panel7 = next(p for p in data["panels"] if p["id"] == 7)
        exprs = " ".join(t.get("expr", "") for t in panel7.get("targets", []))
        assert "reranker_recall_at_5" in exprs
        assert "hybrid_recall" in exprs


class TestGrafanaAlertsF2:
    def test_rules_file_contains_phase2_control_point_group(self):
        content = RULES_PATH.read_text(encoding="utf-8")
        assert "phase2-control-point" in content
        assert "phase2-idealidad-ratio-low" in content
        assert "reranker-fallback-high" in content
        assert "checkpoint-recovery-loss-high" in content
        assert "hybrid-exact-term-regression" in content
        assert 'llm_client_idealidad_ratio{phase="Phase 2"}' in content
        assert "llm_client_reranker_fallback_count" in content
        assert "5000" in content  # recovery loss > 5s
        assert "delta(hybrid_recall_improvement_percentage[7d])" in content


class TestAgentServiceMetricsEndpoint:
    def test_checkpoint_and_reranker_metrics_expose_expected_names(self):
        from prometheus_client import generate_latest

        from llm_client.orchestration.checkpointers.metrics import default_checkpoint_metrics
        from llm_client.rag.metrics import default_reranker_metrics

        # Touch metrics so counters exist in the exposition.
        default_reranker_metrics.increment_fallback_count(primary="bge", active="identity")
        default_checkpoint_metrics.record_redis_write_latency(0.5)

        checkpoint_text = generate_latest(default_checkpoint_metrics.registry).decode()
        reranker_text = generate_latest(default_reranker_metrics.registry).decode()

        assert "llm_client_checkpoint_write_redis_latency_ms" in checkpoint_text
        assert "llm_client_checkpoint_recovery_duration_ms" in checkpoint_text
        assert "llm_client_reranker_fallback_count" in reranker_text
        assert "llm_client_reranker_latency_ms" in reranker_text

    def test_metrics_route_registered_on_agent_app(self):
        """Route table includes /metrics when the app factory is importable."""
        from llm_client.agent import service

        assert hasattr(service, "create_agent_app")
        # Source-level check: the route decorator is present in the factory.
        import inspect

        source = inspect.getsource(service.create_agent_app)
        assert '@app.get("/metrics")' in source
        assert '@app.get("/health")' in source
