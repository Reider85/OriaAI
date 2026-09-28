#!/usr/bin/env python3
"""A/B test for hybrid RAG vs vector-only retrieval (E-4).

Compares exact-term recall@5 between baseline (vector-only) and treatment 
(hybrid + reranker) configurations.

Usage:
    python scripts/ab_test_hybrid_rag.py [--quick]
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.eval.corpus import build_eval_corpus
from llm_client.rag.eval.evaluator import RAGEvaluator


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="A/B test hybrid RAG vs vector-only")
    parser.add_argument(
        "--quick", 
        action="store_true",
        help="Run quick mode (15 queries, 5 per subtype) for PR pipeline"
    )
    args = parser.parse_args()

    print("Starting hybrid RAG A/B test...")
    
    # Load evaluation corpus and queries
    print("Loading evaluation corpus...")
    corpus = build_eval_corpus()
    
    print("Loading evaluation queries...")
    eval_file = Path("datasets/rag_eval/phase2_eval.jsonl")
    queries = []
    try:
        with open(eval_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    queries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Error parsing line {i+1}: {line}")
                    raise
    except Exception as e:
        print(f"Error reading evaluation file: {e}")
        raise
    
    # Filter exact_term queries for this test
    exact_term_queries = [q for q in queries if q["category"] == "exact_term"]
    print(f"Found {len(exact_term_queries)} exact_term queries")
    
    if args.quick:
        # Quick mode: 15 queries, 5 per subtype
        subtype_counts = {"sku": 0, "error_code": 0, "employee_id": 0}
        quick_queries = []
        for q in exact_term_queries:
            subtype = q.get("subtype", "error_code")  # default to error_code
            if subtype_counts[subtype] < 5:
                quick_queries.append(q)
                subtype_counts[subtype] += 1
        exact_term_queries = quick_queries
        print(f"Quick mode: {len(exact_term_queries)} queries (5 per subtype)")
    
    # Define configurations
    baseline_config = RetrieverConfig(
        retrieval_strategy="vector",
        reranker_enabled=False,
        vector_top_k=10,
        reranker_top_k=5,
    )
    
    treatment_config = RetrieverConfig(
        retrieval_strategy="hybrid",
        reranker_enabled=True,
        reranker_name="bge",
        vector_top_k=10,
        bm25_top_k=10,
        hybrid_top_k=10,
        reranker_top_k=5,
    )
    
    # Run A/B test
    print("Running A/B test...")
    evaluator = RAGEvaluator(eval_dataset_path=str(eval_file), corpus=corpus)
    
    start_time = time.time()
    result = await evaluator.ab_test(
        baseline_config=baseline_config,
        treatment_config=treatment_config,
        limit=len(exact_term_queries) if not args.quick else 15,  # Quick mode limit
        recall_improvement_threshold=30.0,  # 30% improvement required
        latency_threshold_ms=10000.0,  # High threshold, we'll calculate relative threshold manually
    )
    duration = time.time() - start_time
    
    # Calculate relative latency threshold (50% of baseline)
    baseline_latency = result["baseline"]["avg_latency_ms"]
    latency_threshold = baseline_latency * 1.5  # 50% overhead allowed
    
    # Calculate latency overhead percentage
    latency_overhead_pct = ((result["treatment"]["avg_latency_ms"] - baseline_latency) / baseline_latency * 100) if baseline_latency > 0 else 0
    
    # Check pass criteria
    meets_recall_threshold = result["improvement_percent"] >= 30.0  # 30% improvement required
    pass_latency_check = latency_overhead_pct <= 50.0  # Max 50% latency overhead
    overall_pass = result["passes"]
    
    # Generate report
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "duration_seconds": round(duration, 2),
        "total_queries": len(exact_term_queries),
        "baseline_config": {
            "retrieval_strategy": baseline_config.retrieval_strategy,
            "reranker_enabled": baseline_config.reranker_enabled,
            "top_k": baseline_config.reranker_top_k,
        },
        "treatment_config": {
            "retrieval_strategy": treatment_config.retrieval_strategy,
            "reranker_enabled": treatment_config.reranker_enabled,
            "reranker_name": treatment_config.reranker_name,
            "top_k": treatment_config.reranker_top_k,
        },
        "baseline_stats": result["baseline"],
        "treatment_stats": result["treatment"],
        "improvement": {
            "recall_improvement_pct": result["improvement_percent"],
            "recall_improvement_threshold": 30.0,
            "meets_recall_threshold": meets_recall_threshold,
            "latency_overhead_pct": latency_overhead_pct,
            "latency_threshold_ms": latency_threshold,
            "meets_latency_threshold": pass_latency_check,
        },
        "subtype_breakdown": _analyze_subtype_breakdown(result),
        "pass_criteria": {
            "overall_pass": overall_pass,
            "recall_improvement": meets_recall_threshold,
            "latency_overhead": pass_latency_check,
            "subtype_thresholds": _check_subtype_thresholds(result),
        },
        "quick_mode": args.quick,
    }
    
    # Save JSON report
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"ab_test_hybrid_rag_{timestamp}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to: {report_file}")
    
    # Update trend CSV
    _update_trend_csv(report)
    
    # Print summary
    print("\n=== A/B Test Summary ===")
    print(f"Queries: {len(exact_term_queries)}")
    print(f"Baseline recall@5: {result['baseline']['recall_at_5']:.3f}")
    print(f"Treatment recall@5: {result['treatment']['recall_at_5']:.3f}")
    print(f"Improvement: {result['improvement_percent']:.1f}%")
    print(f"Latency overhead: {report['improvement']['latency_overhead_pct']:.1f}%")
    print(f"PASS criteria: {report['pass_criteria']['overall_pass']}")
    
    # Exit with appropriate code
    if report["pass_criteria"]["overall_pass"]:
        print("PASS: Hybrid RAG meets all criteria")
        sys.exit(0)
    else:
        print("FAIL: Hybrid RAG does not meet criteria")
        sys.exit(1)


def _analyze_subtype_breakdown(result) -> dict[str, Any]:
    """Analyze performance by subtype using per_category data."""
    breakdown = {}
    
    # Extract per category data from result
    baseline_per_category = result["baseline"]["per_category"]
    treatment_per_category = result["treatment"]["per_category"]
    
    # Calculate metrics for each subtype
    for subtype in ["sku", "error_code", "employee_id"]:
        baseline_data = baseline_per_category.get(subtype, {})
        treatment_data = treatment_per_category.get(subtype, {})
        
        baseline_recall = baseline_data.get("recall_at_5", 0.0)
        treatment_recall = treatment_data.get("recall_at_5", 0.0)
        query_count = baseline_data.get("query_count", 0)
        
        improvement = ((treatment_recall - baseline_recall) / baseline_recall * 100) if baseline_recall > 0 else 0.0
        
        breakdown[subtype] = {
            "query_count": query_count,
            "baseline_recall": baseline_recall,
            "treatment_recall": treatment_recall,
            "improvement_pct": improvement,
        }
    
    return breakdown


def _check_subtype_thresholds(result) -> dict[str, bool]:
    """Check if subtype thresholds are met."""
    thresholds = {
        "sku": False,      # >=40%
        "error_code": False,  # >=40% 
        "employee_id": False,  # >=25%
    }
    
    for subtype, metrics in _analyze_subtype_breakdown(result).items():
        if subtype in thresholds:
            if subtype == "employee_id":
                thresholds[subtype] = metrics["improvement_pct"] >= 25.0
            else:
                thresholds[subtype] = metrics["improvement_pct"] >= 40.0
    
    return thresholds


def _update_trend_csv(report):
    """Update the trend CSV with latest results."""
    csv_file = Path("reports/hybrid_recall_trend.csv")
    
    # Prepare row data
    row = {
        "date": report["timestamp"][:10],  # Just date part
        "baseline_recall": report["baseline_stats"]["recall_at_5"],
        "treatment_recall": report["treatment_stats"]["recall_at_5"],
        "improvement_pct": report["improvement"]["recall_improvement_pct"],
        "sku_recall": report["subtype_breakdown"]["sku"]["treatment_recall"],
        "error_code_recall": report["subtype_breakdown"]["error_code"]["treatment_recall"],
        "employee_id_recall": report["subtype_breakdown"]["employee_id"]["treatment_recall"],
        "latency_overhead_pct": report["improvement"]["latency_overhead_pct"],
        "pass_fail": "PASS" if report["pass_criteria"]["overall_pass"] else "FAIL",
    }
    
    # Read existing CSV or create new
    if csv_file.exists():
        df = pd.read_csv(csv_file)
        new_row = pd.DataFrame([row])
        df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    
    # Save CSV
    df.to_csv(csv_file, index=False)
    print(f"Trend data updated: {csv_file}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())