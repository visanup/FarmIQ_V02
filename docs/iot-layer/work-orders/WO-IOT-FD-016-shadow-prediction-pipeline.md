# Work Order: WO-IOT-FD-016 - Cloud Model Subscription and Edge Prediction Pipeline End-to-End

**Work Order ID**: `WO-IOT-FD-016`  
**Ticket**: `IOT-FD-016`  
**Epic**: `EPIC-IOT-FD-04` AI Weight Prediction Enablement  
**Owner Role**: `Node Edge Engineer` and `ML Engineer`  
**Suggested Assignee**: Edge Runtime Engineering and Applied ML Engineering  
**Suggested Reviewer**: Lead Software Architect, ML Lead, Product Owner for WeighVision  
**Priority**: P2  
**Status**: Completed with Docker-backed end-to-end verification  
**Created**: 2026-07-13  
**Last Updated**: 2026-07-14  
**Estimated Effort**: 16-24 hours  
**Execution Model**: cross-functional implementation with staged rollout

---

## Objective

Implement a Cloud-managed model subscription path where Edge pulls the approved package and executes local shadow prediction without overriding operational ground truth.

## Business Outcome

Cloud now governs package selection and approval, while Edge executes locally to avoid unnecessary transfer and prediction cost.

## Implementation Status

Implemented:

- effective package resolution through `edge-policy-sync`
- package pull from local path, `file://`, or HTTP(S)
- checksum validation before activation
- extracted package caching under `MODEL_CACHE_DIR`
- active and fallback manifest persistence
- `POST /api/v1/inference/models/refresh` for on-demand activation refresh
- local shadow inference from normalized features
- outbox payload enrichment with model and package metadata

Edge sync-back metadata now includes:

- `package_id`
- `package_version`
- `feature_schema_version`
- `activation_source`
- `fallback_engaged`
- `prediction_mode`
- `features_used`

Verification summary:

- unit tests prove activation and sync-back behavior
- real package artifact from `WO-IOT-FD-015` was activated and executed locally in shadow mode
- Batch 5 Docker E2E proof verified Cloud subscription -> Edge local shadow inference -> Cloud readmodel sync-back

## Agent Skill Profile

### Primary

- `Node Edge Engineer`
- `ML Engineer`

### Supporting

- `Data Engineer`
- `Documentation Agent`

## Code Areas

- `edge-layer/edge-vision-inference/app/inference_service.py`
- `edge-layer/edge-vision-inference/app/job_service.py`
- `edge-layer/edge-vision-inference/app/api/v1/endpoints.py`
- `edge-layer/edge-vision-inference/tests/test_inference_service.py`
- `edge-layer/edge-vision-inference/tests/test_job_service.py`
- `edge-layer/edge-weighvision-session/src/controllers/sessionController.ts`
- `edge-layer/edge-weighvision-session/src/services/sessionService.ts`
- `edge-layer/edge-policy-sync/src/services/policySyncService.ts`
- `cloud-layer/cloud-api-gateway-bff/src/controllers/weighvisionController.ts`
- `cloud-layer/cloud-api-gateway-bff/src/services/weighvisionService.ts`
- `cloud-layer/cloud-weighvision-readmodel/src/services/weighvisionService.ts`
- `scripts/batch5-e2e-smoke.ps1`

## Scope

### In Scope

- Cloud model registry and subscription control
- Edge model pull, checksum validation, activation, and fallback
- local shadow inference using normalized features
- sync-back metadata for audit and evaluation

### Out of Scope

- replacing operational final weight
- mandatory Cloud-hosted prediction execution
- automatic decision-path override

## Dependencies

- `WO-IOT-FD-014`
- `WO-IOT-FD-015`
- `WO-IOT-FD-017`
- `WO-IOT-FD-018`
- `WO-IOT-FD-019`
- `WO-IOT-FD-020`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| bad package activation breaks Edge inference runtime | operational instability | checksum validation plus fallback manifest path |
| sync-back lacks enough metadata for model audit | unusable experiment evidence | enforce package and feature-schema fields in outbox payload |
| shadow package is mistaken for operational truth | business regression | keep `shadow_mode_only` policy and never override finalized load-cell path |

## Implementation Plan Outcome

1. Cloud registry and subscription APIs were integrated into the Edge activation flow.
2. Edge activation now caches and loads the selected package.
3. Shadow inference now consumes normalized features from the latest capture metadata.
4. Sync-back payload now records package, version, activation, and feature metadata.
5. BFF weighvision read paths now forward `Authorization`, `x-request-id`, and `x-trace-id` to the readmodel.
6. Batch 5 smoke now uses UUID event IDs for outbox-backed flows and proves acked prediction events correctly.

## Required End-to-End Evidence

Delivered:

- one exported package artifact from `WO-IOT-FD-015`
- one package activation proof on Edge runtime
- one local shadow inference result from the real exported package
- one sync-back payload assertion with package and feature metadata
- one Cloud readmodel session showing finalized truth and independent shadow prediction in the same session timeline

## Test Plan

### Verification Completed

- `python -m pytest tests/test_inference_service.py`
- `python -m pytest tests/test_job_service.py`
- `npx jest --runInBand --coverage=false tests/services/weighvisionService.spec.ts tests/controllers/weighvisionController.spec.ts`
- real package smoke activation using the exported field-baseline artifact
- Docker-backed Batch 5 E2E proof using `scripts/batch5-e2e-smoke.ps1`

### Optional Follow-up

- full Docker Compose proof across Cloud and Edge services in one integrated run

## Rollback Plan

- switch subscription to fallback package or leave Edge in stub mode
- preserve historical shadow prediction records and acknowledgement history
- do not change live weighing ownership during rollback

## Deliverables

- Edge package activation runtime
- Edge shadow prediction execution path
- sync-back metadata enrichment
- model refresh endpoint

## Acceptance Criteria

- Edge can generate shadow predictions from a Cloud-governed package without changing the live weighing decision path
- Edge can surface activation and fallback metadata for audit
- Edge can sync package and feature-schema metadata back with `inference.completed`
- Cloud readmodel can return the same session with both finalized truth and shadow prediction evidence

## Evidence Required

- [batch4-control-plane-verification-2026-07-14.md](../evidence/batch4-control-plane-verification-2026-07-14.md)
- [batch5-e2e-smoke-2026-07-14.md](../evidence/batch5-e2e-smoke-2026-07-14.md)
- [12-cloud-edge-ai-control-plane-pack.md](../12-cloud-edge-ai-control-plane-pack.md)
