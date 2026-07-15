# Work Order: WO-IOT-FD-015 - Baseline Weight Prediction Models and Deployable Model Package

**Work Order ID**: `WO-IOT-FD-015`  
**Ticket**: `IOT-FD-015`  
**Epic**: `EPIC-IOT-FD-04` AI Weight Prediction Enablement  
**Owner Role**: `ML Engineer`  
**Suggested Assignee**: Applied ML Engineering  
**Suggested Reviewer**: ML Lead, Lead Software Architect  
**Priority**: P2  
**Status**: Completed with baseline-v1 evidence  
**Created**: 2026-07-13  
**Last Updated**: 2026-07-14  
**Estimated Effort**: 14-20 hours  
**Execution Model**: experiment-driven work with dataset governance

---

## Objective

Train and evaluate a real Cloud baseline model for chicken weight prediction, then publish a deployable model package for Edge subscription and shadow execution.

## Business Outcome

Cloud now owns a working training and packaging path, while Edge can consume the resulting package format without changing operational final-weight ownership.

## Implementation Status

Implemented:

- `POST /api/v1/ml/weighvision/train-baseline`
- baseline training over a CSV dataset using the canonical feature contract
- validation and naive-comparator metrics in the API response
- deployable `.tar.gz` package export
- package registry record creation
- package download endpoint

Current baseline-v1 artifact:

- package version: `wv-shadow-field-baseline-2026.07.14`
- dataset: `docs/iot-layer/evidence/batch2-weight-audit-dataset.csv`
- artifact path: `cloud-layer/cloud-ml-model-service/artifacts/weighvision/tenant-batch4-real/wv-shadow-field-baseline-2026.07.14.tar.gz`

Observed metric summary:

- train `mae_kg = 2.78364`
- validation `mae_kg = 7.49596`
- naive validation `mae_kg = 2.647279`

Decision:

- the training and packaging pipeline is complete
- this linear baseline is not promotion-ready because it underperforms the naive comparator on validation data
- the package remains valid for Batch 4 shadow-path verification

## Agent Skill Profile

### Primary

- `ML Engineer`

### Supporting

- `Data Engineer`
- `QA Benchmark Agent`

## Code Areas

- `cloud-layer/cloud-ml-model-service/app/weighvision_baseline.py`
- `cloud-layer/cloud-ml-model-service/app/routes.py`
- `cloud-layer/cloud-ml-model-service/app/schemas.py`
- `cloud-layer/cloud-ml-model-service/tests/test_api.py`

## Scope

### In Scope

- one real baseline training route
- metric emission for train, validation, and naive comparator
- deployable package artifact export
- package checksum publication
- package registry integration

### Out of Scope

- multi-family production model search
- online retraining scheduler
- dashboard model-quality presentation

## Dependencies

- `WO-IOT-FD-014`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| feature leakage or invalid split inflates confidence | false promotion | keep time-based split and explicit validation metrics |
| exported package format drifts from Edge runtime expectations | activation failure | keep package manifest contract and activation smoke evidence |
| poor baseline quality is mistaken for production readiness | operational regression | keep package shadow-only until metrics improve |

## Implementation Plan Outcome

1. Dataset contract was used as the training interface.
2. Baseline model was trained and evaluated.
3. Metrics were recorded against a naive comparator.
4. Deployable package artifact was exported and registered.
5. Package download contract was published for Edge activation.

## Test Plan

### Verification Completed

- API tests confirm the train-baseline route exports a package and download endpoint
- package manifest now emits `entrypoint = model/model.json`
- real field-audit dataset was used to produce one artifact and metric set

### Remaining Follow-up

- benchmark stronger model families against the same dataset before any broader promotion

## Rollback Plan

- do not promote a package beyond shadow mode if validation remains worse than the naive comparator
- keep the current package registry entry for audit, but pin Edge subscriptions to fallback or prior known-good package when necessary

## Deliverables

- baseline-v1 training route
- metric summary
- deployable package artifact
- package registry record
- package download endpoint

## Acceptance Criteria

- one baseline can be trained from the Cloud dataset contract
- one deployable package artifact can be exported and downloaded
- one metric summary is published with train, validation, and naive comparator results

## Evidence Required

- [batch4-control-plane-verification-2026-07-14.md](../evidence/batch4-control-plane-verification-2026-07-14.md)
- `cloud-layer/cloud-ml-model-service/artifacts/weighvision/tenant-batch4-real/wv-shadow-field-baseline-2026.07.14.tar.gz`
