# Work Order: WO-IOT-FD-002 - Final Weight Path Reconstruction

**Work Order ID**: `WO-IOT-FD-002`  
**Ticket**: `IOT-FD-002`  
**Epic**: `EPIC-IOT-FD-01` Weight Estimation Validation  
**Owner Role**: `Repo Auditor`  
**Suggested Assignee**: Edge Integration Audit  
**Suggested Reviewer**: Lead Software Architect, Edge Service Owner  
**Priority**: P0  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 6-10 hours  
**Execution Model**: single primary agent with architecture review

---

## Objective

Reconstruct the exact path that produces `final_weight_kg` for one session from IoT event creation to Edge database persistence.

## Business Outcome

The team must be able to explain abnormal final values using code-backed evidence rather than inference.

## Agent Skill Profile

### Primary

- `Repo Auditor`

### Supporting

- `Architecture Analyst`
- `Documentation Agent`

## Code Areas

- `iot-layer/weight-vision-service/app/processor.py`
- `iot-layer/weight-vision-service/app/session_client.py`
- `edge-layer/edge-ingress-gateway/src/ingress/processor.ts`
- `edge-layer/edge-weighvision-session/src/controllers/sessionController.ts`
- `edge-layer/edge-weighvision-session/src/services/sessionService.ts`

## Scope

### In Scope

- trace `weighvision.session.finalized`
- map ingress payload transformation
- trace finalize logic into stored session fields
- compare `initial_weight_kg`, `final_weight_kg`, and `session_weights.weight_kg`

### Out of Scope

- changing calculation logic
- changing schema design
- benchmark work

## Dependencies

- none

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| payload is transformed in multiple layers | unclear root cause | document event shape per hop |
| code path differs between MQTT and direct HTTP | incomplete audit | compare both ingress and direct session API paths |
| final value falls back to inferred defaults | hidden bias | explicitly document fallback rules in finalize logic |

## Implementation Plan

1. Capture the payload emitted by `weight-vision-service`.
2. Trace ingress routing and body transformation.
3. Trace `edge-weighvision-session/finalize` input and fallback logic.
4. Map stored DB fields to source payloads and code branches.
5. Publish one sequence diagram and source-of-truth note.

## Test Plan

### Static Verification

- confirm event field names from source code
- confirm DB target fields from Prisma schema and service logic

### Flow Verification

- trace at least one session with explicit final weight
- trace at least one session where fallback logic applies

### Regression Guardrails

- documentation must include code references for every conclusion
- no conclusion should rely on assumption without a code citation

## Rollback Plan

- no production rollback required
- if analysis is wrong, invalidate the sequence note and regenerate from source code paths

## Deliverables

- final-weight path sequence diagram
- source-of-truth mapping note
- ambiguity list, if any

## Acceptance Criteria

- one finalized session path is explained without ambiguity
- stored final value is traceable to code and payload

## Evidence Required

- code references
- payload examples
- DB field mapping summary

## Completion Note

Completed in Batch 2 investigation.

Primary evidence:

- [08-weight-estimation-audit-pack.md](../08-weight-estimation-audit-pack.md)
- [09-final-weight-local-smoke-runbook.md](../09-final-weight-local-smoke-runbook.md)
- `iot-layer/weight-vision-service/app/processor.py`
- `edge-layer/edge-weighvision-session/src/controllers/sessionController.ts`
- `edge-layer/edge-weighvision-session/src/services/sessionService.ts`
- `cloud-layer/cloud-weighvision-readmodel/src/services/weighvisionService.ts`

Completion summary:

- reconstructed the finalized weight fallback order from IoT payload to Edge session persistence
- closed the nested `payload.scale.weight_kg` gap on Edge finalize intake
- proved the finalized path end-to-end locally with session `sess-fw-20260714-113013`
