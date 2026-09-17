#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_BASE="${EDGE_DIR}/docker-compose.yml"
COMPOSE_DEV="${EDGE_DIR}/docker-compose.dev.yml"

COMMAND="${1:-ps}"
shift || true

WITH_FEED_INTAKE=false
WITH_VOLUMES=false
SERVICE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-feed-intake)
      WITH_FEED_INTAKE=true
      ;;
    --volumes)
      WITH_VOLUMES=true
      ;;
    *)
      SERVICE="$1"
      ;;
  esac
  shift || true
done

compose_args=(-f "$COMPOSE_BASE" -f "$COMPOSE_DEV")
if [[ "$WITH_FEED_INTAKE" == "true" ]]; then
  compose_args+=(--profile feed-intake)
fi

compose() {
  docker compose "${compose_args[@]}" "$@"
}

case "$COMMAND" in
  up)
    compose up -d --build
    ;;
  down)
    if [[ "$WITH_VOLUMES" == "true" ]]; then
      compose down -v
    else
      compose down
    fi
    ;;
  ps)
    compose ps
    ;;
  logs)
    if [[ -n "$SERVICE" ]]; then
      compose logs -f --tail=200 "$SERVICE"
    else
      compose logs -f --tail=200
    fi
    ;;
  seed)
    if [[ "$WITH_FEED_INTAKE" == "true" ]]; then
      "${EDGE_DIR}/scripts/run-seeds.sh" --with-feed-intake
    else
      "${EDGE_DIR}/scripts/run-seeds.sh"
    fi
    ;;
  smoke-http)
    "${EDGE_DIR}/scripts/edge-smoke-http.sh"
    ;;
  smoke-mqtt)
    "${EDGE_DIR}/scripts/edge-smoke-mqtt.sh"
    ;;
  config)
    compose config
    ;;
  validate)
    test -f "$COMPOSE_BASE"
    test -f "$COMPOSE_DEV"
    test -f "${EDGE_DIR}/scripts/run-seeds.sh"
    test -f "${EDGE_DIR}/scripts/edge-smoke-http.sh"
    test -f "${EDGE_DIR}/scripts/edge-smoke-mqtt.sh"
    compose config >/dev/null
    services="$(compose config --services)"
    if [[ -z "$services" ]]; then
      echo "Compose service list is empty" >&2
      exit 1
    fi
    if [[ "$WITH_FEED_INTAKE" == "true" ]] && ! grep -qx "edge-feed-intake" <<<"$services"; then
      echo "feed-intake profile requested but edge-feed-intake is missing from compose output" >&2
      exit 1
    fi
    echo "Validation OK"
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    exit 1
    ;;
esac
