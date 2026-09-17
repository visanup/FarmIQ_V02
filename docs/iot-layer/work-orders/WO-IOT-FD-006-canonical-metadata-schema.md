# Work Order: WO-IOT-FD-006 - Canonical Metadata Schema

**Work Order ID**: `WO-IOT-FD-006`  
**Ticket**: `IOT-FD-006`  
**Epic**: `EPIC-IOT-FD-02` Metadata Pipeline Verification  
**Owner Role**: `Architecture Analyst`  
**Suggested Assignee**: Architecture and Contracts Lead  
**Suggested Reviewer**: Lead Software Architect, Data Lead  
**Priority**: P0  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 8-12 hours  
**Execution Model**: architecture-first with repo audit support

---

## Objective

Define one authoritative schema for WeighVision capture metadata across IoT, Edge, and Cloud layers.

## Business Outcome

This schema is the contract that prevents metadata loss, field ambiguity, and unstable downstream analytics and Cloud prediction behavior.

## Agent Skill Profile

### Primary

- `Architecture Analyst`

### Supporting

- `Repo Auditor`
- `Data Engineer`

## Code Areas

- `iot-layer/weight-vision-capture/run_service.py`
- `iot-layer/weight-vision-service/app/processor.py`
- `edge-layer/edge-ingress-gateway/src/ingress/processor.ts`
- `edge-layer/edge-weighvision-session/prisma/schema.prisma`
- `edge-layer/edge-vision-inference/app/db.py`
- `cloud-layer/cloud-ingestion`
- `cloud-layer/cloud-analytics-service`

## Scope

### In Scope

- define required and optional fields
- define units, names, and versioning
- define raw vs normalized ownership
- define Edge-to-Cloud mapping expectations across services

### Out of Scope

- implementing persistence changes
- model benchmarking
- dashboard visualization work

## Dependencies

- none

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| current field names are inconsistent | future mapping errors | establish canonical names and aliases |
| semantic overlap between depth and distance | analytics confusion | define exact field semantics and units |
| downstream services ignore optional fields | silent data loss | document consumer expectations explicitly |

## Implementation Plan

1. Inventory current metadata fields from capture outputs and message payloads.
2. Define canonical names, units, and requiredness.
3. Separate raw-only, normalized, and derived fields.
4. Define schema versioning and compatibility rules.
5. Publish contract and ownership map.

## Test Plan

### Contract Verification

- every required field must have a known source
- every normalized field must define unit and meaning

### Consumer Verification

- review current IoT, Edge, and Cloud consumers against the contract
- identify fields that are emitted but not consumed

### Regression Guardrails

- future contract changes must require explicit version increment or compatibility note

## Rollback Plan

- if the schema proposal is rejected, retain current de facto schema behavior and record unresolved ambiguities
- do not promote dependent implementation tickets until schema approval is complete

## Deliverables

- canonical schema document
- example payload
- ownership and mapping table

## Acceptance Criteria

- every requested feature field has a defined source, unit, and semantic meaning

## Evidence Required

- schema table
- example JSON
- field ownership map

## Completion Note

Completed in Batch 1 traceability hardening.

Primary evidence:

- [contracts/weighvision-capture-metadata.contract.md](../../contracts/weighvision-capture-metadata.contract.md)
- [06-metadata-verification-pack.md](../06-metadata-verification-pack.md)
