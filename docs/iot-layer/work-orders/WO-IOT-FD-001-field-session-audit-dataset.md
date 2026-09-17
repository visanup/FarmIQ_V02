# Work Order: WO-IOT-FD-001 - Field Session Audit Dataset

**Work Order ID**: `WO-IOT-FD-001`  
**Ticket**: `IOT-FD-001`  
**Epic**: `EPIC-IOT-FD-01` Weight Estimation Validation  
**Owner Role**: `Data Engineer`  
**Suggested Assignee**: Edge Data Engineering  
**Suggested Reviewer**: Lead Software Architect, Edge Platform Lead  
**Priority**: P0  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 8-12 hours  
**Execution Model**: single primary agent with auditor support

---

## Objective

Create a repeatable audit dataset that joins field sessions, load-cell values, capture metadata, and final persisted Edge values.

## Business Outcome

This dataset becomes the factual baseline for anomaly investigation, parameter validation, and future AI training readiness.

## Agent Skill Profile

### Primary

- `Data Engineer`

### Supporting

- `Repo Auditor`
- `Documentation Agent`

## Code Areas

- `iot-layer/weight-vision-capture/data/metadata/*.json`
- `edge-layer/edge-weighvision-session/prisma/schema.prisma`
- `edge-layer/edge-weighvision-session/src/services/sessionService.ts`
- `iot-layer/weight-vision-service/app/processor.py`

## Scope

### In Scope

- extract representative field sessions
- join `weight_sessions`, `session_weights`, media bindings, and capture metadata
- define anomaly labels and audit columns
- produce one repeatable extraction path

### Out of Scope

- fixing capture logic
- changing Edge persistence schema
- model retraining

## Dependencies

- none

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| missing join key between metadata and Edge session | dataset becomes incomplete | define canonical join rule before extraction |
| inconsistent field names across sources | wrong analytics output | publish column dictionary with source mapping |
| overfitting to a tiny sample | misleading conclusions | require normal and anomalous session coverage |

## Implementation Plan

1. Identify minimum viable session sample for anomaly study.
2. Define source-of-truth join keys across metadata, session, and weight tables.
3. Build extraction query or script.
4. Export analysis-ready dataset and document columns.
5. Publish anomaly shortlist with traceable source references.

## Test Plan

### Static Verification

- confirm all referenced tables and files exist
- verify every exported column maps to a known source

### Data Verification

- confirm one anomalous session can be traced end-to-end
- confirm one normal session can be traced end-to-end
- verify no row exists without a source session identifier

### Regression Guardrails

- rerunning extraction must produce deterministic schema
- extraction must not depend on manual spreadsheet edits

## Rollback Plan

- no production rollback required for this work order
- if extraction logic is wrong, discard generated dataset and rerun from source records

## Deliverables

- audit dataset extract
- column dictionary
- extraction query or script
- anomaly shortlist

## Acceptance Criteria

- at least one auditable dataset exists for abnormal sessions
- each row traces to a session ID and source capture artifact
- extraction can be rerun without manual-only steps

## Evidence Required

- sample output rows
- source query or script path
- note on data completeness gaps

## Completion Note

Completed in Batch 2 investigation.

Primary evidence:

- [08-weight-estimation-audit-pack.md](../08-weight-estimation-audit-pack.md)
- `iot-layer/scripts/build_weight_session_audit_dataset.py`
- `docs/iot-layer/evidence/batch2-weight-audit-dataset.csv`
- `docs/iot-layer/evidence/batch2-weight-audit-summary.json`

Completion summary:

- extraction generated one repeatable audit dataset from `129` field metadata files
- dataset exposed missing weight, unstable weight, multi-detection, low-confidence, and depth-outlier categories used by downstream Batch 2 analysis
