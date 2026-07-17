#!/bin/bash
set -euo pipefail

MODE="full"
COMPOSE_FILE="docker-compose.dev.yml"
RUN_SEEDS=0
FROM_BATCH="infra"
TO_BATCH="gateway"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUD_LAYER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_PATH="$CLOUD_LAYER_DIR/$COMPOSE_FILE"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/deploy.sh [full|batched|verify|down] [options]

Options:
  --compose-file <file>  Compose file to use (default: docker-compose.dev.yml)
  --run-seeds            Run seeds after startup
  --from-batch <name>    Batched mode start: infra|core|pipeline|domain|analytics|gateway
  --to-batch <name>      Batched mode end: infra|core|pipeline|domain|analytics|gateway
EOF
}

if [[ $# -gt 0 && "$1" != --* ]]; then
  MODE="$1"
  shift
fi

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
      shift 2
      ;;
    --to-batch)
      TO_BATCH="$2"
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

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker command not found" >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_PATH" ]]; then
  echo "ERROR: compose file not found: $COMPOSE_PATH" >&2
  exit 1
fi

ensure_docker_network() {
  local network_name="${1:-farmiq-net}"
  if ! docker network ls --format '{{.Name}}' | grep -qx "$network_name"; then
    echo "Creating Docker network '$network_name'..."
    docker network create "$network_name" >/dev/null
  fi
}

case "$MODE" in
  full)
    ensure_docker_network
    docker compose -f "$COMPOSE_PATH" up -d --build
    if [[ "$RUN_SEEDS" -eq 1 ]]; then
      powershell -ExecutionPolicy Bypass -File "$SCRIPT_DIR/04-run-seeds.ps1"
    fi
    ;;
  batched)
    args=(--compose-file "$COMPOSE_FILE" --from-batch "$FROM_BATCH" --to-batch "$TO_BATCH")
    if [[ "$RUN_SEEDS" -eq 1 ]]; then
      args+=(--run-seeds)
    fi
    "$SCRIPT_DIR/03-dev-up-batched.sh" "${args[@]}"
    ;;
  verify)
    "$SCRIPT_DIR/verify-compose.sh" "$COMPOSE_FILE"
    curl -fsS http://localhost:5125/api/health >/dev/null
    status="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:5125/api/v1/tenants || true)"
    if [[ "$status" != "200" && "$status" != "401" ]]; then
      echo "ERROR: /api/v1/tenants returned HTTP $status" >&2
      exit 1
    fi
    ;;
  down)
    docker compose -f "$COMPOSE_PATH" down
    ;;
  *)
    echo "ERROR: invalid mode '$MODE'" >&2
    usage
    exit 1
    ;;
esac
