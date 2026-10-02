#!/bin/bash

# ci-local-quick.sh — Run PR pipeline locally (cross-platform)
# Equivalent to scripts/ci-local-quick.ps1 but for Unix-like systems (Git Bash, WSL, macOS, Linux)

set -euo pipefail

# Configuration
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
RUNTIME_DIR="${REPO_ROOT}/.runtime"
TEST_RESULTS_DIR="${REPO_ROOT}/test-results"
PYTHON_EXE=""
TIMEOUT_SECONDS=300
KEEP_INFRA=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default targets
TARGETS=("all")
PORT=8501

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        lint|typecheck|unit|integration|checkpoint|bm25|reranker|hybrid-rag|web-search|rag-query|ui|all)
            TARGETS=("$1")
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT_SECONDS="$2"
            shift 2
            ;;
        --keep-infra)
            KEEP_INFRA=1
            shift
            ;;
        --help)
            echo "Usage: $0 [TARGETS...] [OPTIONS]"
            echo "  TARGETS: lint, typecheck, unit, integration, checkpoint, bm25, reranker, hybrid-rag, web-search, rag-query, ui, all"
            echo "  OPTIONS:"
            echo "    --port PORT        Streamlit UI port (default: 8501)"
            echo "    --timeout SEC     Timeout in seconds (default: 300)"
            echo "    --keep-infra      Don't tear down infrastructure after tests"
            echo "    --help            Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Find Python executable
find_python() {
    local candidates=()
    
    # Try virtual environment first
    if [[ -f "${REPO_ROOT}/.venv/bin/python" ]]; then
        candidates+=("${REPO_ROOT}/.venv/bin/python")
    fi
    
    # Try common system paths
    for version in "313" "312" "311" "310" "3.13" "3.12" "3.11" "3.10"; do
        if command -v "python${version}" &>/dev/null; then
            candidates+=("python${version}")
        fi
    done
    
    # Try generic python3/python
    for cmd in "python3" "python"; do
        if command -v "${cmd}" &>/dev/null; then
            # Check version
            if "${cmd}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
                candidates+=("${cmd}")
            fi
        fi
    done
    
    # Try candidates
    for candidate in "${candidates[@]}"; do
        if "${candidate}" -c "import sys; print(sys.version)" &>/dev/null; then
            PYTHON_EXE="${candidate}"
            return 0
        fi
    done
    
    log_error "Python 3.11+ was not found. Install Python or create .venv in the project root."
    return 1
}

# Find Docker executable
find_docker() {
    if command -v docker &>/dev/null; then
        return 0
    fi
    
    # Try common Docker Desktop paths (for Windows)
    local docker_paths=(
        "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
        "/mnt/c/Users/${USER}/AppData/Local/Docker/resources/bin/docker.exe"
        "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
        "C:/Users/${USER}/AppData/Local/Docker/resources/bin/docker.exe"
    )
    
    for path in "${docker_paths[@]}"; do
        if [[ -f "${path}" ]]; then
            export DOCKER_EXE="${path}"
            return 0
        fi
    done
    
    log_error "Docker was not found. Install Docker Desktop."
    return 1
}

# Wait for service to be healthy
wait_for_service() {
    local service_name="$1"
    local url="$2"
    local max_attempts=30
    local attempt=1
    
    log_info "Waiting for ${service_name} to be ready..."
    
    while [[ ${attempt} -le ${max_attempts} ]]; do
        if curl -f "${url}" &>/dev/null; then
            log_info "${service_name} is ready!"
            return 0
        fi
        
        log_info "Waiting for ${service_name}... (${attempt}/${max_attempts})"
        sleep 2
        ((attempt++))
    done
    
    log_error "${service_name} did not become ready after ${max_attempts} attempts"
    return 1
}

# Start infrastructure
start_infrastructure() {
    log_info "Starting infrastructure..."
    
    # Create directories
    mkdir -p "${RUNTIME_DIR}" "${TEST_RESULTS_DIR}"
    
    # Start services
    docker compose -f "${COMPOSE_FILE}" up -d
    
    # Wait for services
    wait_for_service "Redis" "http://localhost:6380/0"
    wait_for_service "MinIO" "http://localhost:9000/minio/health/live"
    wait_for_service "Vault" "http://localhost:8200/v1/sys/health"
    wait_for_service "PostgreSQL" "postgresql://postgres:postgres@localhost:5434/llm_client"
    
    log_info "Infrastructure is ready!"
}

# Stop infrastructure
stop_infrastructure() {
    if [[ ${KEEP_INFRA} -eq 1 ]]; then
        log_info "Keeping infrastructure running (use --keep-infra to change this behavior)"
        return
    fi
    
    log_info "Stopping infrastructure..."
    docker compose -f "${COMPOSE_FILE}" down
}

# Run tests
run_tests() {
    local target="$1"
    
    case "${target}" in
        lint)
            log_info "Running lint (ruff)..."
            "${PYTHON_EXE}" -m ruff check src tests
            ;;
        typecheck)
            log_info "Running typecheck (mypy)..."
            "${PYTHON_EXE}" -m mypy src/llm_client
            ;;
        unit)
            log_info "Running unit tests + coverage..."
            "${PYTHON_EXE}" -m pytest tests/unit --maxfail=1 \
                --cov=src/llm_client \
                --cov-report=term-missing \
                --cov-report=xml \
                --cov-report=html
            ;;
        integration)
            log_info "Running integration tests..."
            "${PYTHON_EXE}" -m pytest tests/integration --maxfail=1
            ;;
        checkpoint)
            log_info "Running checkpoint latency test..."
            "${PYTHON_EXE}" -m pytest tests/staging_load/test_checkpoint_latency.py::test_checkpoint_latency_p99_below_2ms -v --tb=short
            ;;
        bm25)
            log_info "Running BM25 indexing regression test..."
            "${PYTHON_EXE}" -c "
import time
from llm_client.rag.eval.corpus import build_eval_corpus
from llm_client.rag.eval.mock_pipeline import MockRetrievalPipeline

print('Testing BM25 indexing performance...')
corpus = build_eval_corpus()

start_time = time.time()
pipeline = MockRetrievalPipeline(corpus)
indexing_time = time.time() - start_time

print(f'BM25 indexing time: {indexing_time:.3f} seconds')
assert indexing_time < 1.0, f'BM25 indexing took {indexing_time:.3f}s, expected <1.0s'
print('✅ BM25 indexing regression test passed')
"
            ;;
        reranker)
            log_info "Running reranker A/B test..."
            "${PYTHON_EXE}" scripts/ab_test_reranker.py --quick
            ;;
        hybrid-rag)
            log_info "Running hybrid RAG A/B test..."
            "${PYTHON_EXE}" scripts/ab_test_hybrid_rag.py --quick
            ;;
        web-search)
            log_info "Running web search integration test..."
            "${PYTHON_EXE}" -m pytest tests/integration/test_web_search_integration.py -v
            ;;
        rag-query)
            log_info "Running RAG query integration test..."
            "${PYTHON_EXE}" -m pytest tests/integration/test_rag_query_integration.py -v
            ;;
        ui)
            log_info "Starting Streamlit UI..."
            "${PYTHON_EXE}" -m streamlit run src/llm_client/ui/app.py --server.port=${PORT} --server.headless=true &
            local ui_pid=$!
            echo "${ui_pid}" > "${RUNTIME_DIR}/streamlit.pid"
            log_info "Streamlit UI started on port ${PORT} (PID: ${ui_pid})"
            log_info "Press Ctrl+C to stop..."
            trap "kill ${ui_pid} 2>/dev/null; exit" INT
            while true; do sleep 1; done
            ;;
        all)
            log_info "Running all targets..."
            run_tests lint
            run_tests typecheck
            run_tests unit
            run_tests integration
            run_tests checkpoint
            run_tests bm25
            run_tests reranker
            run_tests hybrid-rag
            run_tests web-search
            run_tests rag-query
            run_tests ui
            ;;
        *)
            log_error "Unknown target: ${target}"
            exit 1
            ;;
    esac
}

# Main execution
main() {
    log_info "Starting ci-local-quick..."
    
    # Find dependencies
    if ! find_python; then
        exit 1
    fi
    
    if ! find_docker; then
        exit 1
    fi
    
    # Set up environment
    export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"
    
    # Start infrastructure (trap to ensure cleanup)
    trap stop_infrastructure EXIT
    
    start_infrastructure
    
    # Run each target
    for target in "${TARGETS[@]}"; do
        log_info "=== Running target: ${target} ==="
        run_tests "${target}"
    done
    
    log_info "ci-local-quick completed successfully!"
}

# Run main function
main "$@"