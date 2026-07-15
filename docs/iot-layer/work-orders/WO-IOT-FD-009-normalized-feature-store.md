# Work Order: WO-IOT-FD-009 - Edge-to-Cloud Normalized Feature Store

**Work Order ID**: `WO-IOT-FD-009`  
**Ticket**: `IOT-FD-009`  
**Epic**: `EPIC-IOT-FD-02` Metadata Pipeline Verification  
**Owner Role**: `Data Engineer`  
**Suggested Assignee**: Edge Data Engineering  
**Suggested Reviewer**: Lead Software Architect, Data Platform Reviewer  
**Priority**: P0  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 14-20 hours  
**Execution Model**: schema-first change with mapping implementation

---

## Objective

Create normalized feature tables and mappings so computer-vision features can be synchronized from Edge to Cloud and queried without manual JSON parsing.

## Business Outcome

This converts raw metadata into analytics-ready and ML-ready features that can be synchronized to Cloud, queried, validated, and reused consistently.

## Agent Skill Profile

### Primary

- `Data Engineer`

### Supporting

- `Architecture Analyst`
- `Node Edge Engineer`

## Code Areas

- Edge DB schema design
- Cloud ingestion contract for normalized features
- `edge-layer/edge-weighvision-session/prisma/schema.prisma`
- raw metadata persistence path from `WO-IOT-FD-008`
- feature mapping logic to be introduced in Edge processing

## Scope

### In Scope

- design normalized feature table structure and Cloud delivery contract
- map area, bbox, width, height, depth, confidence, and related fields
- decide per-detection or selected-object granularity
- provide mapping implementation path

### Out of Scope

- AI model training
- cloud warehouse redesign outside the agreed ingestion boundary
- dashboard analytics UI

## Dependencies

- `WO-IOT-FD-006`
- `WO-IOT-FD-008`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| wrong granularity choice | unusable feature store | decide per-detection vs selected-object explicitly |
| unit mismatch between raw and normalized fields | bad analytics and ML features | enforce canonical units from approved schema |
| tight coupling to one model version | future migration pain | store model-agnostic geometric features separately |

## Implementation Plan

1. Define normalized feature entities and keys at Edge.
2. Map raw metadata fields to typed columns and Cloud-ready payloads.
3. Implement mapping path or mapper job.
4. Define Cloud ingestion expectations for synchronized features.
5. Add query examples and validation checks.
6. Publish mapping spec for downstream users.

## Test Plan

### Static Verification

- validate every normalized column against the canonical schema
- confirm unit definitions and nullability rules

### Runtime Verification

- map one full raw metadata payload into normalized rows
- verify queried columns match source values
- verify synchronized payload shape is Cloud-consumable

### Regression Guardrails

- feature mapping must not require manual JSON parsing downstream
- schema changes must preserve traceability back to raw metadata

## Rollback Plan

- if normalized design is rejected, keep raw metadata persistence only
- rollback mapper deployment while preserving stored raw metadata
- do not promote Cloud feature ingestion until contract approval is complete

## Deliverables

- feature table schema
- Cloud ingestion contract
- mapping implementation
- field mapping specification

## Acceptance Criteria

- requested feature fields are queryable in typed columns and available for Cloud synchronization

## Evidence Required

- schema design
- example normalized rows
- mapping rules summary

## Completion Note

Completed in Batch 1 traceability hardening.

Validated outputs:

- normalized feature mapping is persisted in typed Edge columns
- normalized feature payload is synchronized in `weighvision.inference.completed`
- Cloud readmodel stores synchronized inference payload for session verification
