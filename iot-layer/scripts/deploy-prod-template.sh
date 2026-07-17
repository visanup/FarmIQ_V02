#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-full}"
SERVICE="${2:-}"
BUILD_IMAGES="${BUILD_IMAGES:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BASE_FILES=(-f docker-compose.yml)
CAPTURE_FILES=(-f docker-compose.yml --profile capture)

run_compose() {
  (
    cd "${IOT_ROOT}"
    docker compose "$@"
  )
}

up_args() {
  local -a args=("$@" up -d)
  if [[ "${BUILD_IMAGES}" == "1" ]]; then
    args+=(--build)
  fi
  printf '%s\n' "${args[@]}"
}

case "${ACTION}" in
  core)
    mapfile -t args < <(up_args "${BASE_FILES[@]}")
    run_compose "${args[@]}" ui-app weight-vision-calibrator weight-vision-service
    ;;
  capture)
    mapfile -t args < <(up_args "${CAPTURE_FILES[@]}")
    run_compose "${args[@]}" weight-vision-capture
    ;;
  full)
    mapfile -t args < <(up_args "${CAPTURE_FILES[@]}")
    run_compose "${args[@]}" ui-app weight-vision-calibrator weight-vision-service weight-vision-capture
    ;;
  status)
    run_compose "${CAPTURE_FILES[@]}" ps
    ;;
  logs)
    if [[ -n "${SERVICE}" ]]; then
      run_compose "${CAPTURE_FILES[@]}" logs -f "${SERVICE}"
    else
      run_compose "${CAPTURE_FILES[@]}" logs -f
    fi
    ;;
  config)
    run_compose "${CAPTURE_FILES[@]}" config
    ;;
  down)
    run_compose "${CAPTURE_FILES[@]}" down --remove-orphans
    ;;
  *)
    echo "Unsupported action: ${ACTION}" >&2
    echo "Use one of: core, capture, full, status, logs, config, down" >&2
    exit 1
    ;;
esac
