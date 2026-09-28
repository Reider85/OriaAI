"""A/B test runner for RAG reranker evaluation."""

import asyncio
import json
import sys
from pathlib import Path

try:
    import aiofiles
except ImportError:
    aiofiles = None

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.eval.evaluator import RAGEvaluator


async def main():
    """Run A/B test comparing baseline vs treatment configurations."""
    # Load evaluation corpus (mock documents)
    corpus = [
        {"id": "doc_1", "content": "Redis connection configuration for high performance applications", "metadata": {"source": "redis_guide"}},
        {"id": "doc_2", "content": "Docker Compose setup for microservices architecture", "metadata": {"source": "docker_guide"}},
        {"id": "doc_3", "content": "Python async/await patterns for concurrent programming", "metadata": {"source": "python_guide"}},
        {"id": "doc_4", "content": "PostgreSQL connection pool configuration best practices", "metadata": {"source": "postgres_guide"}},
        {"id": "doc_5", "content": "Prometheus metrics monitoring setup and configuration", "metadata": {"source": "prometheus_guide"}},
        {"id": "doc_6", "content": "LangChain agent workflow design and implementation", "metadata": {"source": "langchain_guide"}},
        {"id": "doc_7", "content": "Streamlit UI performance optimization techniques", "metadata": {"source": "streamlit_guide"}},
        {"id": "doc_8", "content": "Redis pub/sub message routing patterns", "metadata": {"source": "redis_pubsub"}},
        {"id": "doc_9", "content": "MinIO S3 storage integration and configuration", "metadata": {"source": "minio_guide"}},
        {"id": "doc_10", "content": "Vault secret management best practices", "metadata": {"source": "vault_guide"}},
        {"id": "doc_11", "content": "Presidio PII detection implementation guide", "metadata": {"source": "presidio_guide"}},
        {"id": "doc_12", "content": "spaCy natural language processing with Python", "metadata": {"source": "spacy_guide"}},
        {"id": "doc_13", "content": "Error handling patterns in distributed systems", "metadata": {"source": "error_handling"}},
        {"id": "doc_14", "content": "Authentication and authorization in microservices", "metadata": {"source": "auth_guide"}},
        {"id": "doc_15", "content": "Database connection pooling configuration", "metadata": {"source": "db_pool"}},
        {"id": "doc_16", "content": "Container orchestration with Kubernetes", "metadata": {"source": "k8s_guide"}},
        {"id": "doc_17", "content": "Load balancing strategies for web applications", "metadata": {"source": "load_balancing"}},
        {"id": "doc_18", "content": "Caching strategies for high performance systems", "metadata": {"source": "caching_guide"}},
        {"id": "doc_19", "content": "Message queuing with RabbitMQ", "metadata": {"source": "rabbitmq_guide"}},
        {"id": "doc_20", "content": "API gateway configuration and routing", "metadata": {"source": "api_gateway"}},
        {"id": "doc_21", "content": "Logging and monitoring architecture", "metadata": {"source": "logging_guide"}},
        {"id": "doc_22", "content": "Security best practices for web applications", "metadata": {"source": "security_guide"}},
        {"id": "doc_23", "content": "Database indexing strategies for performance", "metadata": {"source": "db_indexing"}},
        {"id": "doc_24", "content": "Microservice communication patterns", "metadata": {"source": "microservice_comm"}},
        {"id": "doc_25", "content": "Container security scanning and monitoring", "metadata": {"source": "container_security"}},
        {"id": "doc_26", "content": "CI/CD pipeline configuration with GitHub Actions", "metadata": {"source": "cicd_guide"}},
        {"id": "doc_27", "content": "Infrastructure as code with Terraform", "metadata": {"source": "terraform_guide"}},
        {"id": "doc_28", "content": "Service mesh configuration and management", "metadata": {"source": "service_mesh"}},
        {"id": "doc_29", "content": "Web application firewall configuration", "metadata": {"source": "waf_config"}},
        {"id": "doc_30", "content": "API rate limiting and throttling", "metadata": {"source": "rate_limiting"}},
        {"id": "doc_31", "content": "Database sharding strategies", "metadata": {"source": "db_sharding"}},
        {"id": "doc_32", "content": "Container networking configuration", "metadata": {"source": "container_networking"}},
        {"id": "doc_33", "content": "Application performance monitoring", "metadata": {"source": "apm_guide"}},
        {"id": "doc_34", "content": "Distributed transaction management", "metadata": {"source": "distributed_tx"}},
        {"id": "doc_35", "content": "GraphQL API design and implementation", "metadata": {"source": "graphql_guide"}},
        {"id": "doc_36", "content": "WebSockets for real-time communication", "metadata": {"source": "websockets"}},
        {"id": "doc_37", "content": "Serverless architecture patterns", "metadata": {"source": "serverless"}},
        {"id": "doc_38", "content": "Event-driven architecture design", "metadata": {"source": "event_driven"}},
        {"id": "doc_39", "content": "Container resource management", "metadata": {"source": "container_resources"}},
        {"id": "doc_40", "content": "Database backup and recovery strategies", "metadata": {"source": "db_backup"}},
        {"id": "doc_41", "content": "API documentation with OpenAPI/Swagger", "metadata": {"source": "api_docs"}},
        {"id": "doc_42", "content": "Content delivery network configuration", "metadata": {"source": "cdn_config"}},
        {"id": "doc_43", "content": "Database replication strategies", "metadata": {"source": "db_replication"}},
        {"id": "doc_44", "content": "Web application security testing", "metadata": {"source": "security_testing"}},
        {"id": "doc_45", "content": "Container orchestration with Docker Swarm", "metadata": {"source": "docker_swarm"}},
        {"id": "doc_46", "content": "API versioning strategies", "metadata": {"source": "api_versioning"}},
        {"id": "doc_47", "content": "Database connection security", "metadata": {"source": "db_security"}},
        {"id": "doc_48", "content": "Container monitoring and logging", "metadata": {"source": "container_monitoring"}},
        {"id": "doc_49", "content": "Web application firewall rules", "metadata": {"source": "waf_rules"}},
        {"id": "doc_50", "content": "Database performance tuning", "metadata": {"source": "db_tuning"}},
        {"id": "doc_51", "content": "API gateway security configuration", "metadata": {"source": "api_gateway_security"}},
        {"id": "doc_52", "content": "Container image optimization", "metadata": {"source": "container_optimization"}},
        {"id": "doc_53", "content": "Database schema design patterns", "metadata": {"source": "db_schema"}},
        {"id": "doc_54", "content": "Web application caching strategies", "metadata": {"source": "web_caching"}},
        {"id": "doc_55", "content": "API authentication methods", "metadata": {"source": "api_auth"}},
        {"id": "doc_56", "content": "Container runtime configuration", "metadata": {"source": "container_runtime"}},
        {"id": "doc_57", "content": "Database query optimization", "metadata": {"source": "db_query_opt"}},
        {"id": "doc_58", "content": "Web application performance testing", "metadata": {"source": "perf_testing"}},
        {"id": "doc_59", "content": "API rate limiting algorithms", "metadata": {"source": "rate_limit_algorithms"}},
        {"id": "doc_60", "content": "Container security best practices", "metadata": {"source": "container_security_best"}},
        {"id": "doc_61", "content": "Database migration strategies", "metadata": {"source": "db_migration"}},
        {"id": "doc_62", "content": "Web application deployment strategies", "metadata": {"source": "deployment_strategies"}},
        {"id": "doc_63", "content": "API documentation generation", "metadata": {"source": "api_doc_gen"}},
        {"id": "doc_64", "content": "Container orchestration with Nomad", "metadata": {"source": "nomad_orchestration"}},
        {"id": "doc_65", "content": "Database connection pooling libraries", "metadata": {"source": "db_pool_libs"}},
        {"id": "doc_66", "content": "Web application monitoring tools", "metadata": {"source": "web_monitoring"}},
        {"id": "doc_67", "content": "API testing strategies", "metadata": {"source": "api_testing"}},
        {"id": "doc_68", "content": "Container resource limits", "metadata": {"source": "container_limits"}},
        {"id": "doc_69", "content": "Database index optimization", "metadata": {"source": "db_index_opt"}},
        {"id": "doc_70", "content": "Web application load testing", "metadata": {"source": "load_testing"}},
        {"id": "doc_71", "content": "API security scanning", "metadata": {"source": "api_security_scan"}},
        {"id": "doc_72", "content": "Container network configuration", "metadata": {"source": "container_network"}},
        {"id": "doc_73", "content": "Database query performance", "metadata": {"source": "db_query_perf"}},
        {"id": "doc_74", "content": "Web application error handling", "metadata": {"source": "web_error_handling"}},
        {"id": "doc_75", "content": "API version management", "metadata": {"source": "api_version_management"}},
        {"id": "doc_76", "content": "Container storage configuration", "metadata": {"source": "container_storage"}},
        {"id": "doc_77", "content": "Database transaction management", "metadata": {"source": "db_tx_management"}},
        {"id": "doc_78", "content": "Web application session management", "metadata": {"source": "session_management"}},
        {"id": "doc_79", "content": "API rate limiting implementation", "metadata": {"source": "rate_limit_implementation"}},
        {"id": "doc_80", "content": "Container security scanning tools", "metadata": {"source": "container_security_tools"}},
        {"id": "doc_81", "content": "Database backup automation", "metadata": {"source": "db_backup_automation"}},
        {"id": "doc_82", "content": "Web application logging strategies", "metadata": {"source": "web_logging"}},
        {"id": "doc_83", "content": "API documentation standards", "metadata": {"source": "api_doc_standards"}},
        {"id": "doc_84", "content": "Container orchestration with Mesos", "metadata": {"source": "mesos_orchestration"}},
        {"id": "doc_85", "content": "Database connection security protocols", "metadata": {"source": "db_security_protocols"}},
        {"id": "doc_86", "content": "Web application security monitoring", "metadata": {"source": "web_security_monitoring"}},
        {"id": "doc_87", "content": "API gateway configuration", "metadata": {"source": "api_gateway_config"}},
        {"id": "doc_88", "content": "Container image scanning", "metadata": {"source": "container_image_scanning"}},
        {"id": "doc_89", "content": "Database performance monitoring", "metadata": {"source": "db_perf_monitoring"}},
        {"id": "doc_90", "content": "Web application caching layers", "metadata": {"source": "web_caching_layers"}},
        {"id": "doc_91", "content": "API authentication protocols", "metadata": {"source": "api_auth_protocols"}},
        {"id": "doc_92", "content": "Container runtime security", "metadata": {"source": "container_runtime_security"}},
        {"id": "doc_93", "content": "Database connection optimization", "metadata": {"source": "db_conn_optimization"}},
        {"id": "doc_94", "content": "Web application security frameworks", "metadata": {"source": "web_security_frameworks"}},
        {"id": "doc_95", "content": "API documentation tools", "metadata": {"source": "api_doc_tools"}},
        {"id": "doc_96", "content": "Container orchestration with Rancher", "metadata": {"source": "rancher_orchestration"}},
        {"id": "doc_97", "content": "Database query optimization techniques", "metadata": {"source": "db_query_opt_tech"}},
        {"id": "doc_98", "content": "Web application performance monitoring", "metadata": {"source": "web_perf_monitoring"}},
        {"id": "doc_99", "content": "API security best practices", "metadata": {"source": "api_security_best"}},
        {"id": "doc_100", "content": "Container security policies", "metadata": {"source": "container_security_policies"}},
    ]
    
    # Initialize evaluator
    dataset_path = "datasets/rag_eval/phase2_eval.jsonl"
    evaluator = RAGEvaluator(dataset_path, corpus)
    
    # Configure baseline (no reranker) and treatment (with reranker)
    baseline_config = RetrieverConfig(
        reranker_enabled=False,
        retrieval_strategy="hybrid",
    )
    
    treatment_config = RetrieverConfig(
        reranker_enabled=True,
        reranker_name="bge",
        retrieval_strategy="hybrid",
    )
    
    # Run A/B test
    print("Running A/B test for RAG reranker evaluation...")
    print(f"Baseline: reranker_enabled={baseline_config.reranker_enabled}")
    print(f"Treatment: reranker_enabled={treatment_config.reranker_enabled}, reranker_name={treatment_config.reranker_name}")
    print()
    
    results = await evaluator.ab_test(baseline_config, treatment_config)
    
    # Print results
    print(f"Baseline Recall@5: {results['baseline']['recall_at_5']:.3f}")
    print(f"Treatment Recall@5: {results['treatment']['recall_at_5']:.3f}")
    print(f"Improvement: {results['improvement_percent']:.1f}%")
    print(f"Latency Overhead: {results['latency_overhead_ms']:.1f}ms")
    print()
    
    print("Per-category results:")
    for category in results['baseline']['per_category']:
        baseline_cat = results['baseline']['per_category'][category]
        treatment_cat = results['treatment']['per_category'][category]
        improvement = ((treatment_cat['recall_at_5'] - baseline_cat['recall_at_5']) / 
                     baseline_cat['recall_at_5'] * 100) if baseline_cat['recall_at_5'] > 0 else 0
        
        print(f"  {category}: Baseline {baseline_cat['recall_at_5']:.3f} → "
              f"Treatment {treatment_cat['recall_at_5']:.3f} (+{improvement:.1f}%)")
    
    print()
    
    # Check pass/fail criteria
    criteria = results['criteria']
    print("Criteria:")
    print(f"  Recall improvement ≥ {criteria['recall_improvement_threshold']}%: "
          f"{'PASS' if criteria['actual_improvement'] >= criteria['recall_improvement_threshold'] else 'FAIL'} "
          f"({criteria['actual_improvement']:.1f}%)")
    print(f"  Latency overhead < {criteria['latency_threshold_ms']}ms: "
          f"{'PASS' if criteria['actual_latency'] < criteria['latency_threshold_ms'] else 'FAIL'} "
          f"({criteria['actual_latency']:.1f}ms)")
    print()
    
    # Save report
    report_path = f"reports/ab_test_reranker_{results['timestamp'].replace(':', '-')}.json"
    Path("reports").mkdir(exist_ok=True)
    
    if aiofiles:
        async with aiofiles.open(report_path, "w") as f:
            await f.write(json.dumps(results, indent=2))
    else:
        # This is acceptable for the script - it's not in a hot path
        # and the alternative would be to make the whole function sync
        with open(report_path, "w") as f:
            json.dump(results, f, indent=2)
    
    print(f"Report saved to: {report_path}")
    
    # Exit with appropriate code
    sys.exit(0 if results['passes'] else 1)


if __name__ == "__main__":
    asyncio.run(main())