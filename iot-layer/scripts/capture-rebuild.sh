#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "[capture] Rebuilding image and recreating service"
docker compose --profile capture build weight-vision-capture
docker compose --profile capture up -d --force-recreate weight-vision-capture
docker ps --filter name=iot-layer-weight-vision-capture-1 --format '{{.Names}}\t{{.Status}}\t{{.RunningFor}}'
