#!/usr/bin/env bash
# Source this file so the verified package hash remains in the current shell.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "Run: source ./ml_weight_prediction/shadow-integration/prepare.sh" >&2
  exit 1
fi
set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_DIR="$SERVICE_ROOT/ml_weight_prediction/artifacts/shadow-package-approved"
if [[ ! -f "$PACKAGE_DIR/manifest.json" ]]; then
  docker run --rm \
    --mount "type=bind,source=$SERVICE_ROOT,target=/work" \
    farmiq-allocation-shadow:local \
    python /work/ml_weight_prediction/scripts/package_model.py \
      --artifact-dir /work/ml_weight_prediction/artifacts/session_20260919_weak_candidate_approved \
      --output-dir /work/ml_weight_prediction/artifacts/shadow-package-approved \
      --performance-standard /work/ml_weight_prediction/docs/performance_standards/arbor_acres_plus/approved/Arbor_Acres_Plus_Male_Performance_Standard.xlsx \
      --version aa-male-20260919-shadow-v1
fi
export ALLOCATION_SHADOW_MANIFEST_SHA256
ALLOCATION_SHADOW_MANIFEST_SHA256="$(sha256sum "$PACKAGE_DIR/manifest.json" | awk '{print $1}')"
printf 'Trusted local package SHA256: %s\n' "$ALLOCATION_SHADOW_MANIFEST_SHA256"
