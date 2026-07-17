#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-core}"
SERVICE="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BASE_FILES=(-f docker-compose.yml)
SMOKE_FILES=(-f docker-compose.yml -f docker-compose.capture-smoke.yml)

run_compose() {
  (
    cd "${IOT_ROOT}"
    docker compose "$@"
  )
}

case "${ACTION}" in
  core)
    run_compose "${BASE_FILES[@]}" up -d --build ui-app weight-vision-calibrator weight-vision-service
    ;;
  full)
    run_compose "${BASE_FILES[@]}" --profile capture up -d --build \
      ui-app weight-vision-calibrator weight-vision-service weight-vision-capture
    ;;
  capture-recreate)
    run_compose "${BASE_FILES[@]}" --profile capture up -d --force-recreate weight-vision-capture
    ;;
  capture-rebuild)
    run_compose "${BASE_FILES[@]}" --profile capture build weight-vision-capture
    run_compose "${BASE_FILES[@]}" --profile capture up -d --force-recreate weight-vision-capture
    ;;
  smoke)
    run_compose "${SMOKE_FILES[@]}" up -d --build weight-vision-capture-smoke
    ;;
  status)
    run_compose "${SMOKE_FILES[@]}" ps
    ;;
  logs)
    if [[ -n "${SERVICE}" ]]; then
      run_compose "${SMOKE_FILES[@]}" logs -f "${SERVICE}"
    else
      run_compose "${SMOKE_FILES[@]}" logs -f
    fi
    ;;
  config)
    run_compose "${BASE_FILES[@]}" config
    ;;
  down)
    run_compose "${SMOKE_FILES[@]}" down --remove-orphans
    ;;
  *)
    echo "Unsupported action: ${ACTION}" >&2
    echo "Use one of: core, full, capture-recreate, capture-rebuild, smoke, status, logs, config, down" >&2
    exit 1
    ;;
esac
