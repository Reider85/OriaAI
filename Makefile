# OriaAI CI — Makefile for local development (cross-platform)
# 
# Usage:
#   make ci-local-quick    # Run PR pipeline locally (lint, typecheck, unit, integration, etc.)
#   make ci-local-staging  # Run staging pipeline locally (checkpoint-latency, A/B tests, etc.)
#   make ci-local-integration-staging  # Run forensic integration staging locally
#   make ci-local          # Alias for ci-local-quick
#
# On Windows: Git Bash / MSYS / WSL required for make. PowerShell scripts (.ps1) remain available.

.PHONY: ci-local ci-local-quick ci-local-staging ci-local-integration-staging

ci-local: ci-local-quick

ci-local-quick:
	bash scripts/ci-local-quick.sh

ci-local-staging:
	bash scripts/ci-local-staging.sh

ci-local-integration-staging:
	bash scripts/ci-local-integration-staging.sh