#!/usr/bin/env bash
# Dev stand-in for AWS S3 Server Access Logging (MVP-PROMPTS E-4, DoD:
# "В dev (MinIO) — access logs доступны через mc admin trace").
#
# MinIO has no native AWS-style access-log format, so `mc admin trace` is the
# dev-mode source. This script captures a trace window and uploads it into the
# forensic bucket under _access_logs/ — the prefix AccessLogIngestor polls.
#
# Note: trace output is JSON, not AWS Server Access Log format; the ingestor
# parser skips unparseable lines (debug log). The production ingestion path is
# covered by tests/integration/test_access_log_ingestor_e2e.py with proper
# AWS-format lines.
#
# Usage: scripts/dev_minio_trace.sh [duration_seconds]   (default 60)

set -euo pipefail

DURATION="${1:-60}"
OUT="trace-$(date +%Y%m%dT%H%M%S).jsonl"

echo "Capturing MinIO access trace for ${DURATION}s..."
timeout "${DURATION}" docker-compose exec -T minio \
  mc admin trace --call access local --json >"/tmp/${OUT}" || true

LINES=$(wc -l <"/tmp/${OUT}" | tr -d ' ')
if [ "${LINES}" -eq 0 ]; then
  echo "No trace captured (no S3 traffic during the window)."
  exit 0
fi

docker-compose cp "/tmp/${OUT}" llm-minio:/tmp/
docker-compose exec minio mc cp "/tmp/${OUT}" \
  "local/llm-client-forensic/_access_logs/${OUT}"
echo "Uploaded ${LINES} lines to _access_logs/${OUT}."
echo "AccessLogIngestor polls this prefix every ACCESS_LOG_POLL_INTERVAL_SECONDS."
