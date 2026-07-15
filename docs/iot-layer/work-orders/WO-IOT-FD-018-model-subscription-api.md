# Work Order: WO-IOT-FD-018 - Model Subscription API

**Work Order ID**: `WO-IOT-FD-018`  
**Ticket**: `IOT-FD-018`  
**Epic**: `EPIC-IOT-FD-04` AI Weight Prediction Enablement  
**Owner Role**: `Node Edge Engineer`  
**Suggested Assignee**: Cloud Edge Control-Plane Engineering  
**Suggested Reviewer**: Lead Software Architect, Edge Platform Lead  
**Priority**: P1  
**Status**: Completed (MVP)  
**Created**: 2026-07-13  
**Estimated Effort**: 12-16 hours  
**Execution Model**: API-first contract with Edge client validation

---

## Objective

Provide a Cloud API that lets Edge sites discover, subscribe to, and retrieve the correct approved model version.

## Business Outcome

This gives the platform controlled model distribution instead of manual model rollout.

## Implementation Status

Implemented in Batch 4 MVP:

- Cloud subscription endpoints added for `PUT`, `GET`, `resolve`, and `ack`
- `cloud-api-gateway-bff` now proxies these WeighVision control-plane endpoints
- `edge-policy-sync` can poll the resolve endpoint and cache the effective subscription per `(tenant_id, site_id)`

Current limitation:

- the API resolves package metadata and policy, but package download orchestration and full activation telemetry still belong to the next execution step

## Agent Skill Profile

### Primary

- `Node Edge Engineer`

### Supporting

- `Architecture Analyst`
- `Documentation Agent`

## Code Areas

- `cloud-layer/cloud-api-gateway-bff`
- `cloud-layer/cloud-weighvision-readmodel`
- Edge subscription client path in `edge-layer/edge-vision-inference`
- optional reuse path in `edge-layer/edge-policy-sync`
- model registry integration from `WO-IOT-FD-017`

## Scope

### In Scope

- subscription create/update/read flow
- site or tenant scoping
- version resolution rules
- Edge pull contract
- subscription audit fields
- compatible package resolution response

### Out of Scope

- model training
- Edge fallback policy implementation
- dashboard administration UI

## Dependencies

- `WO-IOT-FD-017`
- `WO-IOT-FD-019`

## Proposed API Surface

| Method | Path | Purpose |
| --- | --- | --- |
| `PUT` | `/api/v1/weighvision/model-subscriptions/sites/{siteId}` | assign or update the desired model channel or pinned version for one site |
| `GET` | `/api/v1/weighvision/model-subscriptions/sites/{siteId}` | read current subscription state for operations and audit |
| `GET` | `/api/v1/weighvision/model-subscriptions/sites/{siteId}/resolve` | resolve the exact approved package Edge should pull now |
| `POST` | `/api/v1/weighvision/model-subscriptions/sites/{siteId}/ack` | optional Edge acknowledgement after download, validation, activation, or rollback |

## Required Resolution Payload

The resolve response should provide enough data for Edge to act without additional guessing:

- `tenant_id`
- `site_id`
- `model_family`
- `model_version`
- `package_uri`
- `package_checksum`
- `runtime_family`
- `runtime_version`
- `feature_schema_version`
- `activation_policy_version`
- `fallback_version`
- `resolved_at`
- `trace_id`

## Design Decisions To Lock

- whether subscription is channel-based such as `stable` and `candidate`, or strictly pinned by version
- whether Edge uses polling, long-polling, or scheduled pull
- whether acknowledgement is mandatory for operational observability
- whether API ownership stays in `cloud-api-gateway-bff` while data ownership lives in a lower-level Cloud service

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| subscription API returns ambiguous version state | Edge activates wrong model | define one resolution rule for active model |
| tenant/site scoping is weak | wrong model reaches wrong site | require explicit scoping keys |
| API contract drifts from package format | Edge pull fails | align with package manifest spec |

## Implementation Plan

1. Define subscription resources and API contract.
2. Define resolution rules for active version per site or tenant.
3. Define Edge pull request and response payloads.
4. Define acknowledgement contract for activation and fallback events.
5. Implement or scaffold API and client contract tests.

## Resolution Rules

- site-level assignment overrides tenant-level default
- pinned rollback version must be explicit if fallback policy requires deterministic local rollback
- unresolved, non-approved, or incompatible versions must return a non-deployable response rather than a silent fallback
- response must be idempotent for the same effective subscription state

## Test Plan

### Static Verification

- verify API contract includes scoping and version metadata

### Runtime Verification

- resolve subscribed version for one Edge site
- reject invalid or unapproved version requests
- verify one Edge acknowledgement event can be recorded without changing subscription intent

### Regression Guardrails

- API must not resolve a model that is not approved and compatible
- API must not return ambiguous multiple active versions for the same site

## Rollback Plan

- disable subscription resolution endpoint if contract is unstable
- fall back to pinned manual version mapping until API is corrected

## Deliverables

- subscription API contract
- implementation plan or scaffold
- Edge client contract
- subscription state model
- sample resolve and acknowledge payloads

## Acceptance Criteria

- an Edge site can resolve which model version it should run using a supported Cloud API

## Evidence Required

- API schema
- sample subscription response
- version resolution rules
- non-deployable response example
