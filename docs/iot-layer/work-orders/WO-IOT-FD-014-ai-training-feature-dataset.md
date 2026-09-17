# Work Order: WO-IOT-FD-014 - Cloud AI Training Feature Dataset

**Work Order ID**: `WO-IOT-FD-014`  
**Ticket**: `IOT-FD-014`  
**Epic**: `EPIC-IOT-FD-04` AI Weight Prediction Enablement  
**Owner Role**: `Data Engineer`  
**Suggested Assignee**: ML Data Engineering  
**Suggested Reviewer**: Lead Software Architect, ML Lead  
**Priority**: P1  
**Status**: Completed (MVP)  
**Created**: 2026-07-13  
**Estimated Effort**: 10-16 hours  
**Execution Model**: schema and extraction design with ML review

---

## Objective

Design the canonical feature dataset used for Cloud-layer AI weight prediction training.

## Business Outcome

This turns synchronized Edge-to-Cloud operational data into a stable Cloud training contract that can support repeatable experiments, model comparison, and deployable model packaging for Edge subscription.

## Implementation Status

Implemented in Batch 4 MVP:

- canonical dataset contract exposed from `cloud-layer/cloud-ml-model-service`
- feature schema version pinned as `wv-feature-schema-v1`
- entity, feature, context, and label fields published through `GET /api/v1/ml/weighvision/dataset-contract`
- downstream BFF proxy path added for WeighVision control-plane clients

Current limitation:

- contract is implemented and test-covered, but a production extraction job over live Cloud-synchronized data is still part of the next WO-IOT-FD-015 or WO-IOT-FD-016 execution step

## Agent Skill Profile

### Primary

- `Data Engineer`

### Supporting

- `ML Engineer`
- `Architecture Analyst`

## Code Areas

- normalized feature store from `WO-IOT-FD-009`
- raw metadata persistence from `WO-IOT-FD-008`
- Cloud training workspace and related ML assets

## Scope

### In Scope

- define features and labels
- define missing-data handling
- define normalization expectations
- define extraction contract for Cloud training

### Out of Scope

- model training implementation
- production prediction serving implementation
- dashboard UI

## Dependencies

- `WO-IOT-FD-009`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| training labels are inconsistent | poor model quality | define label hierarchy and source-of-truth rules |
| feature leakage enters dataset | misleading metrics | separate operational context from forbidden future information |
| extraction is not reproducible | experiments cannot be trusted | version dataset schema and extraction logic |

## Implementation Plan

1. Define feature columns and target labels for Cloud training.
2. Define unit, nullability, and normalization rules.
3. Define extraction and split expectations.
4. Publish dataset schema and feature dictionary.

## Test Plan

### Schema Verification

- every feature must map to normalized or raw source fields
- every label must define source-of-truth and fallback rule

### Extraction Verification

- produce one sample Cloud-ready extract successfully
- confirm schema is stable across reruns

### Regression Guardrails

- no model training without approved dataset schema
- all feature definitions must be versionable

## Rollback Plan

- if dataset design is rejected, retain the normalized feature store without promoting a Cloud training contract
- invalidate unapproved extracts and regenerate under the approved schema

## Deliverables

- dataset schema
- feature dictionary
- extraction specification

## Acceptance Criteria

- the team can generate a repeatable Cloud training dataset from synchronized production-like data

## Evidence Required

- dataset schema draft
- extraction example
- feature dictionary
