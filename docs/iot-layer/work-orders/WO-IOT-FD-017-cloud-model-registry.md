# Work Order: WO-IOT-FD-017 - Cloud Model Registry

**Work Order ID**: `WO-IOT-FD-017`  
**Ticket**: `IOT-FD-017`  
**Epic**: `EPIC-IOT-FD-04` AI Weight Prediction Enablement  
**Owner Role**: `Architecture Analyst` and `ML Engineer`  
**Suggested Assignee**: Cloud ML Platform Engineering  
**Suggested Reviewer**: Lead Software Architect, ML Lead  
**Priority**: P1  
**Status**: Completed (MVP)  
**Created**: 2026-07-13  
**Estimated Effort**: 12-18 hours  
**Execution Model**: control-plane design first, then service implementation

---

## Objective

Design and implement the Cloud-side source of truth for model versions, metadata, approval state, and deployability.

## Business Outcome

This establishes a governed model registry so Edge sites can subscribe only to approved, traceable model versions.

## Implementation Status

Implemented in Batch 4 MVP:

- model package registry persistence added to `cloud-layer/cloud-ml-model-service`
- registry entities implemented through `ml_model_package`
- list, create, and get APIs now exist for WeighVision model packages
- approval state and channel filtering are enforced in package resolution flow

Current limitation:

- registry is currently implemented inside `cloud-ml-model-service` as the first control-plane landing zone, not yet split into a dedicated registry service

## Agent Skill Profile

### Primary

- `Architecture Analyst`
- `ML Engineer`

### Supporting

- `Node Edge Engineer`
- `Documentation Agent`

## Code Areas

- `cloud-layer/cloud-feature-store`
- `cloud-layer/cloud-api-gateway-bff`
- `cloud-layer/cloud-weighvision-readmodel`
- Cloud-side model metadata store or new registry component

## Scope

### In Scope

- model metadata schema
- model version lifecycle
- approval and active-state rules
- model lookup for subscription workflows
- artifact-to-registry linkage
- compatibility and checksum metadata ownership

### Out of Scope

- Edge activation behavior
- runtime fallback logic
- dashboard UX redesign

## Dependencies

- `WO-IOT-FD-014`
- `WO-IOT-FD-015`

## Design Decisions To Lock

- whether the registry is implemented inside `cloud-feature-store` first or as a dedicated Cloud service later
- whether subscription lookup is resolved directly by registry tables or through `cloud-api-gateway-bff`
- which scope is authoritative for rollout: `tenant_id`, `farm_id`, `site_id`, or a combination
- which approval states are mandatory before Edge can see a version as deployable

## Proposed Registry Entities

| Entity | Purpose | Minimum fields |
| --- | --- | --- |
| `model_families` | logical model line for weight prediction | `id`, `name`, `task_type`, `status` |
| `model_versions` | immutable version records | `id`, `model_family_id`, `version`, `training_dataset_version`, `feature_schema_version`, `runtime_family`, `runtime_version`, `checksum`, `package_uri`, `status` |
| `model_approvals` | approval and governance evidence | `id`, `model_version_id`, `approval_state`, `approved_by`, `approved_at`, `evaluation_summary`, `rollback_notes` |
| `model_deployability_rules` | compatibility and rollout constraints | `id`, `model_version_id`, `min_edge_runtime`, `hardware_profile`, `supported_camera_profile`, `supported_feature_schema_versions` |

## Proposed Lifecycle States

`draft` -> `validated` -> `approved` -> `published` -> `deprecated` -> `retired`

Rules:

- only `published` versions are eligible for subscription resolution
- `approved` must require evidence from `WO-IOT-FD-015`
- `deprecated` versions remain queryable for audit but must not be assigned to new sites by default

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| registry lacks approval semantics | unsafe model rollout | require explicit approval and publish states |
| model metadata is incomplete | Edge cannot validate compatibility | require runtime and checksum metadata in registry |
| registry ownership is unclear | long-term maintenance risk | define service ownership before implementation |

## Implementation Plan

1. Define registry entity model and states.
2. Define required model metadata fields.
3. Define publish, approve, deprecate, and active-version rules.
4. Map the first implementation target to existing Cloud services.
5. Implement or scaffold the registry service/path.

## Interface Notes

- Internal write path may originate from Cloud training or release automation.
- Read path should support downstream subscription resolution by site or tenant.
- Registry records should not expose raw package URLs to unauthorized callers without scoped access rules.

## Test Plan

### Static Verification

- verify registry schema includes version, checksum, runtime compatibility, and approval state

### Runtime Verification

- publish one model entry successfully
- resolve one approved model version successfully
- reject one non-approved version from deployable lookup

### Regression Guardrails

- unapproved models must not be returned as deployable

## Rollback Plan

- keep registry behind a non-production flag until approval workflow is stable
- if rejected, retain packaged model artifacts without exposing them to subscription flows

## Deliverables

- registry schema
- lifecycle rules
- implementation plan or service scaffold
- sample registry record set
- control-plane ownership note

## Acceptance Criteria

- one approved model version can be published and discovered by downstream subscription workflows

## Evidence Required

- schema draft
- state model
- sample published model record
- deployability lookup example
