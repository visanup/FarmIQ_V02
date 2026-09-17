# API Contracts

This folder contains human-readable and machine-readable contracts for key APIs and cross-layer data contracts used across FarmIQ.

## Contents

- `weighvision-capture-metadata.contract.md` - canonical WeighVision capture metadata contract
- `weighvision-model-control-plane.contract.md` - Cloud-Edge AI control-plane contract for dataset, package, subscription, and activation policy
- `cloud-bff.yaml` - BFF contract
- `cloud-standards-service.openapi.yaml` - Standards service OpenAPI 3.0 contract
- `cloud-standards-service.contract.md` - Standards service (via BFF) contract
- `cloud-analytics-service.contract.md` - Analytics service contract
- `cloud-llm-insights-service.contract.md` - LLM insights service contract
- `cloud-ml-model-service.contract.md` - ML model service contract
- `cloud-api-gateway-bff.contract.md` - BFF public contract
- `cloud-notification-service.contract.md` - Notification service contract
- `cloud-ingestion.contract.md` - Cloud ingestion contract
- `notifications.payload.md` - canonical notifications payload mapping
- `feed-service.contract.md` - Feed domain contract
- `barn-records-service.contract.md` - Barn records contract
- `tenant-registry-sensors.contract.md` - Sensors contract

## Usage

- Contracts are used for:
  - frontend integration
  - contract testing and mocking
  - documentation and review
  - cross-layer data governance

## Doc Change Summary

### 2026-07-14

- Added canonical WeighVision capture metadata contract for Batch 1 traceability work.
- Added WeighVision Cloud-Edge AI control-plane contract for Batch 4 MVP work.

### 2025-12-27

- Added or updated analytics, LLM insights, and notifications contract docs.

## Next Implementation Steps

1. Keep WeighVision metadata contract aligned with `session_capture_metadata` storage and Cloud readmodel payloads.
2. Add schema-validation tooling if the event schema registry is expanded for WeighVision metadata events.
