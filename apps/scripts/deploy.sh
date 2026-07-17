#!/bin/bash
set -euo pipefail

MODE="up"
TARGET="all"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLOUD_BASE_COMPOSE="$ROOT_DIR/cloud-layer/docker-compose.yml"
CLOUD_DEV_COMPOSE="$ROOT_DIR/cloud-layer/docker-compose.dev.yml"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/deploy.sh [up|down|verify] [all|dashboard-web|admin-web]
EOF
}

if [[ $# -gt 0 ]]; then
  MODE="$1"
  shift
fi

if [[ $# -gt 0 ]]; then
  TARGET="$1"
  shift
fi

case "$TARGET" in
  dashboard-web)
    SERVICES=(dashboard-web)
    ;;
  admin-web)
    SERVICES=(admin-web)
    ;;
  all)
    SERVICES=(dashboard-web admin-web)
    ;;
  *)
    echo "ERROR: invalid target '$TARGET'" >&2
    usage
    exit 1
    ;;
esac

ensure_docker_network() {
  local network_name="${1:-farmiq-net}"
  if ! docker network ls --format '{{.Name}}' | grep -qx "$network_name"; then
    echo "Creating Docker network '$network_name'..."
    docker network create "$network_name" >/dev/null
  fi
}

case "$MODE" in
  up)
    ensure_docker_network
    docker compose -f "$CLOUD_BASE_COMPOSE" -f "$CLOUD_DEV_COMPOSE" --profile ui up -d --build "${SERVICES[@]}"
    ;;
  down)
    docker compose -f "$CLOUD_BASE_COMPOSE" -f "$CLOUD_DEV_COMPOSE" stop "${SERVICES[@]}"
    ;;
  verify)
    for service in "${SERVICES[@]}"; do
      case "$service" in
        dashboard-web)
          curl -fsS http://localhost:5142 >/dev/null
          ;;
        admin-web)
          curl -fsS http://localhost:5143 >/dev/null
          ;;
      esac
    done
    ;;
  *)
    echo "ERROR: invalid mode '$MODE'" >&2
    usage
    exit 1
    ;;
esac
