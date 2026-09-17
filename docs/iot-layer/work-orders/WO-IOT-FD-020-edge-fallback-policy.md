# Work Order: WO-IOT-FD-020 - Edge Fallback and Version Activation Policy

**Work Order ID**: `WO-IOT-FD-020`  
**Ticket**: `IOT-FD-020`  
**Epic**: `EPIC-IOT-FD-04` AI Weight Prediction Enablement  
**Owner Role**: `Node Edge Engineer` and `Architecture Analyst`  
**Suggested Assignee**: Edge Runtime Engineering  
**Suggested Reviewer**: Lead Software Architect, Operations Reviewer  
**Priority**: P1  
**Status**: Completed (MVP)  
**Created**: 2026-07-13  
**Estimated Effort**: 10-14 hours  
**Execution Model**: runtime policy definition before full rollout

---

## Objective

Ensure Edge can activate a subscribed model safely and fall back deterministically if the new version fails.

## Business Outcome

This protects farm operations from unstable model upgrades while preserving Cloud-managed control.

## Implementation Status

Implemented in Batch 4 MVP:

- activation and fallback policy is carried inside the resolved package manifest
- `edge-vision-inference` now reports activation source, fallback engagement, package identity, and policy metadata
- `edge-policy-sync` caches the resolved subscription state that tells Edge which package to prefer and which fallback package is allowed

Current limitation:

- fallback is currently policy-aware at manifest level; the full automatic package rollback and shadow prediction execution path remains part of WO-IOT-FD-016 follow-through

## Agent Skill Profile

### Primary

- `Node Edge Engineer`
- `Architecture Analyst`

### Supporting

- `QA Benchmark Agent`
- `Documentation Agent`

## Code Areas

- `edge-layer/edge-vision-inference`
- Edge runtime activation logic
- Edge version pinning and fallback behavior
- subscription API client integration
- prediction sync status path in `edge-layer/edge-sync-forwarder`

## Scope

### In Scope

- version activation rules
- health checks before activation
- fallback trigger rules
- rollback target selection
- local pinning and staged activation state
- Cloud acknowledgement semantics for activation outcome

### Out of Scope

- model training
- registry schema ownership
- dashboard policy UI

## Dependencies

- `WO-IOT-FD-018`
- `WO-IOT-FD-019`

## Proposed Activation States

`resolved` -> `downloaded` -> `validated` -> `staged` -> `active`

Failure branches:

- `download_failed`
- `validation_failed`
- `activation_failed`
- `rolled_back`

## Proposed Fallback Order

1. revert to the last known-good active version for the same model family
2. if unavailable, revert to the site-pinned fallback version returned by subscription resolution
3. if unavailable, disable AI prediction while leaving the core weighing workflow operational

## Policy Decisions To Lock

- what constitutes a "known-good" version on one Edge site
- whether health is checked only at load time or also after a prediction canary window
- whether fallback is automatic, operator-approved, or split by severity
- how long the Edge node may run on a pinned local version when Cloud is unreachable

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| fallback chooses an invalid version | outage or degraded quality | define explicit fallback precedence |
| activation health checks are too weak | unstable model goes live | require pre-activation validation gates |
| rollback logic is manual only | slow recovery in field | define deterministic automatic and operator-driven fallback |

## Implementation Plan

1. Define activation states and validation gates.
2. Define fallback triggers and rollback target selection.
3. Define version pinning behavior for Edge runtime.
4. Define Cloud acknowledgement payload for success, rejection, and rollback.
5. Publish runtime decision rules and operator guidance.

## Minimum Fallback Triggers

- package checksum mismatch
- unsupported runtime compatibility
- model load failure on `edge-vision-inference`
- repeated prediction failure above threshold during controlled activation
- corrupted local package files
- operator-issued rollback request

## Operational Guardrails

- fallback must not delete historical prediction outputs
- fallback must not block load-cell-based final session processing
- runtime must emit enough state to let Cloud distinguish `resolved-but-not-active` from `active-and-healthy`

## Test Plan

### Static Verification

- verify activation and fallback states are explicit

### Runtime Verification

- accept one valid subscribed model version
- reject one invalid model version
- fall back to the previous valid version successfully
- verify core weighing continues when AI prediction is disabled after fallback

### Regression Guardrails

- failed activation must not block core weighing workflow

## Rollback Plan

- retain previous pinned model version as fallback target
- disable new version activation while preserving subscription metadata if runtime instability occurs

## Deliverables

- activation policy
- fallback policy
- runtime decision rules
- activation state machine summary
- fallback event payload example

## Acceptance Criteria

- Edge runtime can decide whether to activate, reject, or roll back a model version using explicit policy

## Evidence Required

- policy table
- state transition summary
- fallback scenario walkthrough
- last-known-good selection example
