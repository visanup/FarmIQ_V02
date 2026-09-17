#!/bin/bash
# FarmIQ Cloud Layer: build/start services in ordered batches.
# Usage:
#   ./scripts/03-dev-up-batched.sh
#   ./scripts/03-dev-up-batched.sh --run-seeds
#   ./scripts/03-dev-up-batched.sh --from-batch domain
#   ./scripts/03-dev-up-batched.sh --from-batch pipeline --to-batch gateway

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUD_LAYER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="docker-compose.dev.yml"
COMPOSE_PATH=""
RUN_SEEDS=0
FROM_BATCH="infra"
TO_BATCH="gateway"
RETRY_INTERVAL_SECONDS=5
MAX_HTTP_RETRIES=24

BATCH_ORDER=(infra core pipeline domain analytics gateway)

usage() {
  cat <<'EOF'
Usage:
  ./scripts/03-dev-up-batched.sh [options]

Options:
  --compose-file <file>       Compose file to use (default: docker-compose.dev.yml)
  --run-seeds                 Run ./scripts/04-run-seeds.ps1 after all selected batches
  --from-batch <name>         Start from batch: infra|core|pipeline|domain|analytics|gateway
  --to-batch <name>           Stop at batch: infra|core|pipeline|domain|analytics|gateway
  --retry-interval <seconds>  Poll interval for health checks (default: 5)
  --max-http-retries <count>  Max health-check retries per service (default: 24)
  --help                      Show this message
EOF
}

validate_batch_name() {
  local name="$1"
  for batch in "${BATCH_ORDER[@]}"; do
    if [[ "$batch" == "$name" ]]; then
      return 0
    fi
  done
  echo "ERROR: invalid batch name '$name'" >&2
  exit 1
}

batch_index() {
  local name="$1"
  local i
  for i in "${!BATCH_ORDER[@]}"; do
    if [[ "${BATCH_ORDER[$i]}" == "$name" ]]; then
      echo "$i"
      return 0
    fi
  done
  return 1
}

ensure_docker_network() {
  local network_name="${1:-farmiq-net}"
  echo "Ensuring Docker network '$network_name' exists..."
  if ! docker network ls --format '{{.Name}}' | grep -qx "$network_name"; then
    docker network create "$network_name" >/dev/null
    echo "  Created '$network_name'"
    return
  fi

  echo "  '$network_name' already exists"
}

wait_postgres_ready() {
  local attempt
  echo "Waiting for postgres..."
  for ((attempt=1; attempt<=MAX_HTTP_RETRIES; attempt++)); do
    if docker compose -f "$COMPOSE_PATH" exec -T postgres pg_isready -U farmiq >/dev/null 2>&1; then
      echo "  postgres is ready"
      return 0
    fi
    sleep "$RETRY_INTERVAL_SECONDS"
  done

  echo "ERROR: postgres did not become ready in time." >&2
  exit 1
}

wait_rabbitmq_ready() {
  local attempt
  echo "Waiting for rabbitmq..."
  for ((attempt=1; attempt<=MAX_HTTP_RETRIES; attempt++)); do
    if docker exec farmiq-cloud-rabbitmq rabbitmqctl status >/dev/null 2>&1; then
      echo "  rabbitmq is ready"
      return 0
    fi
    sleep "$RETRY_INTERVAL_SECONDS"
  done

  echo "ERROR: rabbitmq did not become ready in time." >&2
  exit 1
}

wait_http_ready() {
  local name="$1"
  local url="$2"
  local attempt
  echo "Waiting for $name..."
  for ((attempt=1; attempt<=MAX_HTTP_RETRIES; attempt++)); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      echo "  $name is ready"
      return 0
    fi
    sleep "$RETRY_INTERVAL_SECONDS"
  done

  echo "ERROR: $name did not become ready in time. Last checked: $url" >&2
  exit 1
}

wait_vault_ready() {
  local attempt
  echo "Waiting for vault..."
  for ((attempt=1; attempt<=12; attempt++)); do
    if curl -fsS --max-time 5 http://127.0.0.1:8200/v1/sys/health >/dev/null 2>&1; then
      echo "  vault is ready"
      return 0
    fi
    sleep "$RETRY_INTERVAL_SECONDS"
  done

  echo "ERROR: vault did not become ready in time." >&2
  exit 1
}

invoke_batch_wait() {
  local batch_name="$1"
  case "$batch_name" in
    infra)
      wait_postgres_ready
      wait_rabbitmq_ready
      wait_vault_ready
      ;;
    core)
      wait_http_ready cloud-identity-access http://localhost:5120/api/health
      wait_http_ready cloud-tenant-registry http://localhost:5121/api/health
      wait_http_ready cloud-standards-service http://localhost:5133/api/health
      wait_http_ready cloud-config-rules-service http://localhost:5126/api/health
      wait_http_ready cloud-audit-log-service http://localhost:5127/api/health
      wait_http_ready cloud-llm-insights-service http://localhost:5134/api/health
      ;;
    pipeline)
      wait_http_ready cloud-ingestion http://localhost:5122/api/health
      wait_http_ready cloud-telemetry-service http://localhost:5123/api/health
      ;;
    domain)
      wait_http_ready cloud-notification-service http://localhost:5128/api/health
      wait_http_ready cloud-feed-service http://localhost:5130/api/health
      wait_http_ready cloud-barn-records-service http://localhost:5131/api/health
      wait_http_ready cloud-weighvision-readmodel http://localhost:5132/api/health
      wait_http_ready cloud-billing-service http://localhost:5145/api/health
      wait_http_ready cloud-reporting-export-service http://localhost:5129/api/health
      ;;
    analytics)
      wait_http_ready cloud-analytics-service http://localhost:5124/api/health
      wait_http_ready cloud-advanced-analytics http://localhost:5146/api/health
      wait_http_ready cloud-data-pipeline http://localhost:5147/api/health
      wait_http_ready cloud-bi-metabase http://localhost:5148/api/health
      ;;
    gateway)
      wait_http_ready cloud-api-gateway-bff http://localhost:5125/api/health
      ;;
  esac
}

invoke_compose_batch() {
  local batch_name="$1"
  shift
  local services=("$@")
  echo
  echo "=== Batch: $batch_name ==="
  echo "Services: ${services[*]}"
  docker compose -f "$COMPOSE_PATH" up -d --build "${services[@]}"
  invoke_batch_wait "$batch_name"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --run-seeds)
      RUN_SEEDS=1
      shift
      ;;
    --from-batch)
      FROM_BATCH="$2"
      validate_batch_name "$FROM_BATCH"
      shift 2
      ;;
    --to-batch)
      TO_BATCH="$2"
      validate_batch_name "$TO_BATCH"
      shift 2
      ;;
    --retry-interval)
      RETRY_INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --max-http-retries)
      MAX_HTTP_RETRIES="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option '$1'" >&2
      usage
      exit 1
      ;;
  esac
done

COMPOSE_PATH="$CLOUD_LAYER_DIR/$COMPOSE_FILE"
if [[ ! -f "$COMPOSE_PATH" ]]; then
  echo "ERROR: compose file not found: $COMPOSE_PATH" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker command not found" >&2
  exit 1
fi

FROM_INDEX="$(batch_index "$FROM_BATCH")"
TO_INDEX="$(batch_index "$TO_BATCH")"
if (( FROM_INDEX > TO_INDEX )); then
  echo "ERROR: --from-batch must come before or equal to --to-batch" >&2
  exit 1
fi

echo "=== FarmIQ Cloud Layer: Batched Build/Up ==="
echo "Compose file: $COMPOSE_PATH"
echo "Batch range : $FROM_BATCH -> $TO_BATCH"
if [[ "$FROM_BATCH" != "infra" ]]; then
  echo "Warning     : earlier batches are assumed to already be running."
fi
echo
echo "Execution plan:"
for ((i=FROM_INDEX; i<=TO_INDEX; i++)); do
  case "${BATCH_ORDER[$i]}" in
    infra)
      echo "  - infra: postgres rabbitmq vault pgadmin"
      ;;
    core)
      echo "  - core: cloud-identity-access cloud-tenant-registry cloud-standards-service cloud-config-rules-service cloud-audit-log-service cloud-llm-insights-service"
      ;;
    pipeline)
      echo "  - pipeline: cloud-ingestion cloud-telemetry-service"
      ;;
    domain)
      echo "  - domain: cloud-notification-service cloud-feed-service cloud-barn-records-service cloud-weighvision-readmodel cloud-billing-service cloud-reporting-export-service"
      ;;
    analytics)
      echo "  - analytics: cloud-analytics-service cloud-advanced-analytics cloud-data-pipeline cloud-bi-metabase"
      ;;
    gateway)
      echo "  - gateway: cloud-api-gateway-bff"
      ;;
  esac
done

ensure_docker_network

for ((i=FROM_INDEX; i<=TO_INDEX; i++)); do
  case "${BATCH_ORDER[$i]}" in
    infra)
      invoke_compose_batch infra postgres rabbitmq vault pgadmin
      ;;
    core)
      invoke_compose_batch core \
        cloud-identity-access \
        cloud-tenant-registry \
        cloud-standards-service \
        cloud-config-rules-service \
        cloud-audit-log-service \
        cloud-llm-insights-service
      ;;
    pipeline)
      invoke_compose_batch pipeline cloud-ingestion cloud-telemetry-service
      ;;
    domain)
      invoke_compose_batch domain \
        cloud-notification-service \
        cloud-feed-service \
        cloud-barn-records-service \
        cloud-weighvision-readmodel \
        cloud-billing-service \
        cloud-reporting-export-service
      ;;
    analytics)
      invoke_compose_batch analytics \
        cloud-analytics-service \
        cloud-advanced-analytics \
        cloud-data-pipeline \
        cloud-bi-metabase
      ;;
    gateway)
      invoke_compose_batch gateway cloud-api-gateway-bff
      ;;
  esac
done

if [[ "$RUN_SEEDS" -eq 1 ]]; then
  powershell -ExecutionPolicy Bypass -File "$SCRIPT_DIR/04-run-seeds.ps1"
fi

echo
echo "All selected batches completed successfully."
