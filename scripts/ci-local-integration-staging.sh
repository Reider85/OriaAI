#!/bin/bash

# ci-local-integration-staging.sh — Run forensic integration staging locally
# Tests forensic path with FORENSIC_STREAM_ENABLED=true + Vault + MinIO

set -euo pipefail

# Configuration
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
RUNTIME_DIR="${REPO_ROOT}/.runtime"
TEST_RESULTS_DIR="${REPO_ROOT}/test-results"
PYTHON_EXE=""
TIMEOUT_SECONDS=600
KEEP_INFRA=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --timeout)
            TIMEOUT_SECONDS="$2"
            shift 2
            ;;
        --keep-infra)
            KEEP_INFRA=1
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "  OPTIONS:"
            echo "    --timeout SEC     Timeout in seconds (default: 600)"
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
    log_info "Starting forensic infrastructure..."
    
    # Create directories
    mkdir -p "${RUNTIME_DIR}" "${TEST_RESULTS_DIR}"
    
    # Start services with forensic environment
    ENVIRONMENT=staging FORENSIC_STREAM_ENABLED=true KMS_PROVIDER=vault \
        docker compose -f "${COMPOSE_FILE}" up -d
    
    # Wait for services
    wait_for_service "Redis" "http://localhost:6380/0"
    wait_for_service "MinIO" "http://localhost:9000/minio/health/live"
    wait_for_service "Vault" "http://localhost:8200/v1/sys/health"
    
    # Initialize Vault transit
    log_info "Initializing Vault transit engine..."
    docker run --rm --network host \
        -e VAULT_ADDR=http://localhost:8200 \
        -e VAULT_TOKEN=root \
        hashicorp/vault:latest \
        sh -c 'vault secrets enable transit && vault write -f transit/keys/forensic-aes256-gcm type=aes256-gcm96'
    
    # Create MinIO buckets + files-only restricted user (BUG-MVP-01 AccessDenied regression)
    log_info "Creating MinIO buckets + files-only restricted user..."
    docker run --rm --network host \
        -e S3_RESTRICTED_ACCESS_KEY \
        -e S3_RESTRICTED_SECRET_KEY \
        quay.io/minio/mc:latest \
        sh -c 'set -e
            mc alias set local http://127.0.0.1:9000 minioadmin minioadmin
            mc mb -p --ignore-existing local/llm-client-forensic
            mc mb -p --ignore-existing local/llm-client-files
            printf "%s" "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:ListBucket\"],\"Resource\":[\"arn:aws:s3:::llm-client-files\",\"arn:aws:s3:::llm-client-files/*\"]}]}" > /tmp/files-only-policy.json
            mc admin policy create local files-only /tmp/files-only-policy.json || mc admin policy add local files-only /tmp/files-only-policy.json || true
            mc admin user create local "${S3_RESTRICTED_ACCESS_KEY:-files-ro}" "${S3_RESTRICTED_SECRET_KEY:-files-ro-secret}" || mc admin user add local "${S3_RESTRICTED_ACCESS_KEY:-files-ro}" "${S3_RESTRICTED_SECRET_KEY:-files-ro-secret}" || true
            mc admin policy attach local files-only --user "${S3_RESTRICTED_ACCESS_KEY:-files-ro}" || mc admin policy set-policy local files-only "${S3_RESTRICTED_ACCESS_KEY:-files-ro}" || true
            mc ls local/'
    
    log_info "Forensic infrastructure is ready!"
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

# Verify docker compose services are running (E-5 precondition)
verify_infrastructure() {
    log_info "Verifying docker compose services are running (docker compose ps)..."
    local ps_output
    if ! ps_output="$(docker compose -f "${COMPOSE_FILE}" ps 2>/dev/null)"; then
        log_error "docker compose ps failed — is Docker running?"
        exit 1
    fi
    if ! echo "${ps_output}" | grep -qE "redis.*running|Running.*redis"; then
        log_error "Redis is not running. Run 'docker compose up -d' before integration tests."
        exit 1
    fi
    log_info "Infrastructure precondition OK."
}

# Phase 3 integration tests (E-5 — explicit 9-test block)
run_phase3_integration_tests() {
    export REDIS_SEMANTIC_CACHE_URL="${REDIS_SEMANTIC_CACHE_URL:-redis://localhost:6380/2}"
    export SEMANTIC_CACHE_ENABLED="${SEMANTIC_CACHE_ENABLED:-true}"
    export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-test-placeholder}"

    local phase3_tests=(
        tests/integration/test_stale_answer_guard.py
        tests/integration/test_semantic_cache_integration.py
        tests/integration/test_facts_extractor_integration.py
        tests/integration/test_cache_aware_llm_integration.py
        tests/integration/test_graph_cache_e2e.py
        tests/integration/test_llm_router_integration.py
        tests/integration/test_react_e2e.py
        tests/integration/test_mcp_server_e2e.py
        tests/integration/test_mcp_server_with_registry.py
    )

    for test_file in "${phase3_tests[@]}"; do
        log_info "Running Phase 3 integration test: ${test_file}"
        if ! "${PYTHON_EXE}" -m pytest "${test_file}" -v --timeout=600; then
            log_error "Phase 3 integration test failed: ${test_file}"
            exit 1
        fi
    done
    log_info "Phase 3 integration tests passed (9/9)."
}

# Run forensic tests
run_forensic_tests() {
    # Set forensic environment
    export ENVIRONMENT=staging
    export FORENSIC_STREAM_ENABLED=true
    export KMS_PROVIDER=vault
    export VAULT_ADDR=http://localhost:8200
    export VAULT_TOKEN=root
    export VAULT_TRANSIT_KEY=forensic-aes256-gcm
    export S3_ENDPOINT=http://localhost:9000
    export S3_ACCESS_KEY=minioadmin
    export S3_SECRET_KEY=minioadmin
    export S3_FORENSIC_BUCKET=llm-client-forensic
    export S3_RESTRICTED_ACCESS_KEY="${S3_RESTRICTED_ACCESS_KEY:-files-ro}"
    export S3_RESTRICTED_SECRET_KEY="${S3_RESTRICTED_SECRET_KEY:-files-ro-secret}"
    export REDIS_URL=redis://localhost:6380/0
    export OPENAI_API_KEY=sk-test-placeholder
    
    log_info "Running forensic e2e test..."
    "${PYTHON_EXE}" -m pytest tests/integration/test_forensic_stream_e2e.py -v --tb=short
    
    log_info "Running integration tests with forensic enabled..."
    "${PYTHON_EXE}" -m pytest tests/integration -m integration --maxfail=1
    
    log_info "Validating staging settings..."
    "${PYTHON_EXE}" -c "
from llm_client.config import Settings
s = Settings()
assert s.environment == 'staging'
assert s.forensic_stream_enabled == True
assert s.kms_provider == 'vault'
assert s.vault_token == 'root'
print('✅ Staging settings validation passed')
"
}

# Main execution
main() {
    log_info "Starting ci-local-integration-staging..."
    
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
    
    # Verify docker compose ps precondition (E-5 anti-pattern guard)
    verify_infrastructure
    
    # Run forensic tests
    run_forensic_tests
    
    # Run Phase 3 integration tests (E-5 explicit 9-test block)
    run_phase3_integration_tests
    
    log_info "ci-local-integration-staging completed successfully!"
}

# Run main function
main "$@"