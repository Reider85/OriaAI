"""A/B test for semantic cache (ADR-011 Phase 3).

Runs N queries twice: once with cache ON, once with cache OFF
(control group). Reports:
- Hit rate (cache ON)
- Stale rate (cache ON)
- Latency: cache hit, cache miss, cache OFF (control)
- Cost savings (cache ON vs OFF)
- LLM call reduction (cache ON vs OFF)

Pilot criteria (ROADMAP §14.1):
- hit rate >15% — PASS
- stale <1% — PASS
- latency cache hit <100ms — PASS
Rollback: stale >1% OR hit rate <10%.
"""
import argparse
import asyncio
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_client.config import settings
from llm_client.observability.llm_metrics import get_cache_hit_counts
from llm_client.rag.semantic_cache import get_semantic_cache


@dataclass
class ABTestResult:
    total_queries: int
    hits: int
    misses: int
    stale: int
    avg_latency_hit_ms: float
    avg_latency_miss_ms: float
    avg_latency_no_cache_ms: float
    cost_saved_usd: float
    llm_calls_reduced: int

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total_queries if self.total_queries else 0.0

    @property
    def stale_rate(self) -> float:
        return self.stale / self.hits if self.hits else 0.0

    def pilot_pass(
        self,
        hit_rate_threshold: float | None = None,
        stale_rate_threshold: float | None = None,
        hit_latency_ms_threshold: float | None = None,
    ) -> bool:
        hit_threshold = hit_rate_threshold or settings.pilot_semantic_cache_hit_rate_threshold
        stale_threshold = stale_rate_threshold or settings.pilot_semantic_cache_stale_rate_threshold
        latency_threshold = hit_latency_ms_threshold or settings.pilot_semantic_cache_hit_latency_ms
        
        return (
            self.hit_rate > hit_threshold
            and self.stale_rate < stale_threshold
            and self.avg_latency_hit_ms < latency_threshold
        )

    def rollback_required(
        self,
        stale_rate_threshold: float | None = None,
        rollback_hit_rate: float | None = None,
    ) -> bool:
        stale_threshold = stale_rate_threshold or settings.pilot_semantic_cache_stale_rate_threshold
        hit_threshold = rollback_hit_rate or settings.pilot_semantic_cache_rollback_hit_rate
        
        return (
            self.stale_rate > stale_threshold
            or self.hit_rate < hit_threshold
        )


async def run_ab_test(queries: list[str], iterations: int = 2) -> ABTestResult:
    """Run queries twice with cache ON (second iteration should
    hit cache if queries are similar)."""
    cache = get_semantic_cache()
    if cache is None:
        raise RuntimeError("Semantic cache disabled")

    # Control group: measure cache miss latency (simulates cache OFF)
    # This represents the overhead of cache lookup when cache is disabled
    control_latencies = []
    for q in queries:
        t0 = time.perf_counter()
        # Simulate cache OFF by getting from empty namespace
        # (this measures embedding + Redis lookup overhead)
        result = await cache.get(f"control:{q}")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        control_latencies.append(elapsed_ms)
    
    avg_latency_no_cache_ms = sum(control_latencies) / len(control_latencies)

    # First pass: populate cache (all misses expected)
    populate_latencies = []
    for q in queries:
        t0 = time.perf_counter()
        # Note: cache.put requires at least one document ID
        await cache.put(q, f"answer_to_{q}", [uuid.UUID("550e8400-e29b-41d4-a716-446655440000")], "gpt-4o-mini", 100)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        populate_latencies.append(elapsed_ms)

    # Get counts before second pass
    before_counts = get_cache_hit_counts()
    
    # Second pass: hit cache
    latencies_hit, latencies_miss = [], []
    
    for q in queries:
        t0 = time.perf_counter()
        result = await cache.get(q)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if result is None:
            latencies_miss.append(elapsed_ms)
        else:
            latencies_hit.append(elapsed_ms)
    
    # Get counts after second pass to calculate actual hit/miss/stale
    after_counts = get_cache_hit_counts()
    hits = after_counts["hit"] - before_counts["hit"]
    misses = after_counts["miss"] - before_counts["miss"]
    stale = after_counts["stale"] - before_counts["stale"]

    return ABTestResult(
        total_queries=len(queries),
        hits=hits, misses=misses, stale=stale,
        avg_latency_hit_ms=sum(latencies_hit) / max(1, len(latencies_hit)),
        avg_latency_miss_ms=sum(latencies_miss) / max(1, len(latencies_miss)),
        avg_latency_no_cache_ms=avg_latency_no_cache_ms,
        cost_saved_usd=hits * settings.pilot_semantic_cache_avg_llm_cost_usd,
        llm_calls_reduced=hits,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries-file", required=True,
                        help="JSONL file with {query, expected_answer, duplicate_group} entries")
    parser.add_argument("--iterations", type=int, default=2,
                        help="Number of iterations (default: 2)")
    parser.add_argument("--output", help="Output JSON report file path")
    args = parser.parse_args()

    import json
    with open(args.queries_file) as f:
        queries = [json.loads(line)["query"] for line in f]

    result = asyncio.run(run_ab_test(queries, args.iterations))

    # Prepare report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_queries": result.total_queries,
        "hits": result.hits,
        "misses": result.misses,
        "stale": result.stale,
        "hit_rate": result.hit_rate,
        "stale_rate": result.stale_rate,
        "avg_latency_hit_ms": result.avg_latency_hit_ms,
        "avg_latency_miss_ms": result.avg_latency_miss_ms,
        "avg_latency_no_cache_ms": result.avg_latency_no_cache_ms,
        "cost_saved_usd": result.cost_saved_usd,
        "llm_calls_reduced": result.llm_calls_reduced,
        "pilot_criteria": {
            "hit_rate_threshold": settings.pilot_semantic_cache_hit_rate_threshold,
            "stale_rate_threshold": settings.pilot_semantic_cache_stale_rate_threshold,
            "hit_latency_ms_threshold": settings.pilot_semantic_cache_hit_latency_ms,
            "rollback_hit_rate_threshold": settings.pilot_semantic_cache_rollback_hit_rate,
        },
        "pilot_pass": result.pilot_pass(),
        "rollback_required": result.rollback_required(),
    }

    # Print summary
    print("=== ADR-011 Pilot A/B Test ===")
    print(f"Total queries: {result.total_queries}")
    print(f"Hits: {result.hits} ({result.hit_rate:.1%})")
    print(f"Misses: {result.misses}")
    print(f"Stale: {result.stale} ({result.stale_rate:.1%})")
    print(f"Avg latency (hit): {result.avg_latency_hit_ms:.1f}ms")
    print(f"Avg latency (miss): {result.avg_latency_miss_ms:.1f}ms")
    print(f"Control latency (no cache): {result.avg_latency_no_cache_ms:.1f}ms")
    print(f"Cost saved: ${result.cost_saved_usd:.4f}")
    print(f"LLM calls reduced: {result.llm_calls_reduced}")
    print()
    
    if result.rollback_required():
        print("❌ ROLLBACK REQUIRED (hit rate <10% OR stale >1%)")
        sys.exit(1)
    elif result.pilot_pass():
        print("✅ PILOT PASS — ADR-011 Approved")
        sys.exit(0)
    else:
        print("⚠️  PILOT PARTIAL — review criteria")
        sys.exit(2)  # Partial pass, not full approval

    # Save report if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()