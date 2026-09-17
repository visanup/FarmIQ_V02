# WeighVision Model Control-Plane Contract

Purpose: Define the implemented Cloud-Edge contract for WeighVision training, package export, subscription resolution, activation, fallback, and shadow sync-back.  
Scope: `cloud-ml-model-service`, `cloud-api-gateway-bff`, `edge-policy-sync`, and `edge-vision-inference`.  
Owner: FarmIQ Edge and Cloud Architecture  
Last updated: 2026-07-14

---

## Overview

The WeighVision AI control plane is split into two responsibilities:

- Cloud owns dataset contract, baseline training, package registry, subscription state, and approval lifecycle.
- Edge owns local package activation, fallback behavior, shadow prediction execution, and sync-back metadata.

Prediction remains Edge-executed. Cloud is the control plane.

---

## Dataset contract endpoint

Cloud source:

- `GET /api/v1/ml/weighvision/dataset-contract`

BFF proxy:

- `GET /api/v1/weighvision/dataset-contract`

Current canonical feature schema version:

- `wv-feature-schema-v1`

Core response fields:

- `contractName`
- `version`
- `featureSchemaVersion`
- `entityKeys`
- `featureFields`
- `contextFields`
- `labelFields`
- `splitPolicy`
- `notes`

---

## Baseline training contract

Cloud source:

- `POST /api/v1/ml/weighvision/train-baseline`

BFF proxy:

- `POST /api/v1/weighvision/train-baseline`

Request fields:

- `datasetPath`
- `packageVersion`
- `channel`
- `approvalState`

Response fields:

- `datasetContract`
- `model`
- `package`
- `datasetPath`
- `datasetRows`
- `trainingRows`
- `validationRows`
- `featureNames`
- `trainMetrics`
- `validationMetrics`
- `naiveMetrics`

---

## Model package registry contract

Cloud source:

- `POST /api/v1/ml/weighvision/model-packages`
- `GET /api/v1/ml/weighvision/model-packages`
- `GET /api/v1/ml/weighvision/model-packages/{packageId}`
- `GET /api/v1/ml/weighvision/model-packages/{packageId}/download`

Registry record fields:

- `id`
- `tenantId`
- `modelId`
- `packageVersion`
- `runtimeFamily`
- `runtimeVersion`
- `featureSchemaVersion`
- `checksumSha256`
- `packageUri`
- `channel`
- `approvalState`
- `manifest`
- `createdAt`
- `updatedAt`

Allowed package channels:

- `stable`
- `candidate`
- `pinned`

Allowed approval states:

- `draft`
- `approved`
- `published`
- `deprecated`

Resolution rule:

- only `published` packages are eligible for non-pinned subscription resolution

---

## Package manifest contract

Current manifest fields:

- `packageVersion`
- `modelFamily`
- `runtimeFamily`
- `runtimeVersion`
- `featureSchemaVersion`
- `checksumSha256`
- `packageUri`
- `entrypoint`
- `channel`
- `activationPolicy`
- `fallbackPolicy`
- `metadata`

Current package layout:

- `manifest.json`
- `model/model.json`
- `schema/feature-schema.json`
- `evidence/metrics-summary.json`

Current required path rule:

- `entrypoint` is relative to the extracted package root
- current trained baseline uses `model/model.json`

Current policy-carrying fields:

- `activationPolicy.require_checksum_validation`
- `activationPolicy.require_feature_schema_match`
- `activationPolicy.max_activation_failures`
- `activationPolicy.activation_mode`
- `fallbackPolicy.order`
- `fallbackPolicy.preserve_shadow_prediction`
- `fallbackPolicy.block_operational_decision_override`

---

## Subscription API contract

Cloud source:

- `PUT /api/v1/ml/weighvision/model-subscriptions/sites/{siteId}`
- `GET /api/v1/ml/weighvision/model-subscriptions/sites/{siteId}`
- `GET /api/v1/ml/weighvision/model-subscriptions/sites/{siteId}/resolve`
- `POST /api/v1/ml/weighvision/model-subscriptions/sites/{siteId}/ack`

BFF proxy:

- `PUT /api/v1/weighvision/model-subscriptions/sites/{siteId}`
- `GET /api/v1/weighvision/model-subscriptions/sites/{siteId}`
- `GET /api/v1/weighvision/model-subscriptions/sites/{siteId}/resolve`
- `POST /api/v1/weighvision/model-subscriptions/sites/{siteId}/ack`

Subscription state fields:

- `tenantId`
- `siteId`
- `farmId`
- `barnId`
- `channel`
- `pinnedPackageId`
- `fallbackPackageId`
- `notes`

Resolve response fields:

- `tenantId`
- `siteId`
- `farmId`
- `barnId`
- `channel`
- `activePackage`
- `fallbackPackage`
- `activationPolicy`
- `fallbackPolicy`

Acknowledgement request fields:

- `tenantId`
- `packageId`
- `ackType`
- `status`
- `detail`
- `payload`

Allowed acknowledgement types:

- `downloaded`
- `validated`
- `activated`
- `rollback`
- `failed`

---

## Edge cache contract

Edge cache owner:

- `edge-layer/edge-policy-sync`

Local cache table:

- `edge_model_subscription_cache`

Cache key:

- `(tenant_id, site_id)`

Cache payload fields:

- `resolved_json`
- `hash`
- `fetched_at`
- `source_etag`
- `last_error`

Readback endpoint:

- `GET /model-subscription/effective?tenantId={tenantId}&siteId={siteId}`

---

## Edge activation and inference contract

Edge runtime owner:

- `edge-layer/edge-vision-inference`

Current configuration fields:

- `MODEL_MANIFEST_PATH`
- `FALLBACK_MODEL_MANIFEST_PATH`
- `MODEL_CACHE_DIR`
- `MODEL_SYNC_ENABLED`
- `POLICY_SYNC_URL`
- `EDGE_TENANT_ID`
- `EDGE_SITE_ID`
- `MODEL_CONTROL_BFF_URL`
- `MODEL_CONTROL_TOKEN`

Refresh endpoint:

- `POST /api/v1/inference/models/refresh`

Activation inputs accepted now:

- local package path
- `file://` package URI
- HTTP(S) package URI

Current runtime info output includes:

- `activation_source`
- `fallback_engaged`
- `package_id`
- `package_version`
- `feature_schema_version`
- `manifest_path`
- `activation_policy`
- `fallback_policy`
- `fallback_package_id`
- `fallback_manifest_path`
- `active_model_path`

Current prediction metadata output includes:

- `prediction_mode`
- `features_used`
- `stub_mode`

Current activation-source semantics:

- `manifest` means active package activated successfully
- `fallback_manifest` means fallback package activated
- `env` means no package activation succeeded and runtime stays on stub defaults

---

## Edge shadow sync-back contract

Owner:

- `edge-layer/edge-vision-inference/app/job_service.py`

Current outbox payload enrichment includes:

- `package_id`
- `package_version`
- `feature_schema_version`
- `activation_source`
- `fallback_engaged`
- `prediction_mode`
- `features_used`

This metadata must travel with `inference.completed` so Cloud can audit:

- which package produced the prediction
- whether fallback was engaged
- which feature schema was used
- whether the output was real shadow inference or stub fallback

---

## Current operating boundary

Implemented now:

- dataset contract
- real baseline training route
- deployable package export
- package registry
- subscription resolve and acknowledgement
- Edge package activation
- Edge local shadow execution
- Edge sync-back metadata enrichment

Still intentionally constrained:

- prediction remains shadow-only
- live weighing and finalized operational weight remain outside model override scope
- current linear baseline quality is not strong enough for promotion beyond plumbing verification
