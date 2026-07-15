# Work Order: WO-IOT-FD-010 - Metadata Verification Report Pack

**Work Order ID**: `WO-IOT-FD-010`  
**Ticket**: `IOT-FD-010`  
**Epic**: `EPIC-IOT-FD-02` Metadata Pipeline Verification  
**Owner Role**: `Documentation Agent`  
**Suggested Assignee**: Technical Documentation and QA Support  
**Suggested Reviewer**: Lead Software Architect, QA Lead  
**Priority**: P1  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 6-10 hours  
**Execution Model**: documentation artifact with engineering review

---

## Objective

Create an operational verification pack for confirming metadata flow from capture JSON to Edge and Cloud persistence.

## Business Outcome

This makes metadata verification repeatable for engineering, QA, and future audits without rediscovering the Edge-to-Cloud flow each time.

## Agent Skill Profile

### Primary

- `Documentation Agent`

### Supporting

- `Repo Auditor`
- `Data Engineer`

## Code Areas

- raw metadata persistence outputs
- normalized feature store outputs
- reference docs under `docs/iot-layer`

## Scope

### In Scope

- create verification checklist
- provide report layout and query examples
- document expected values and known failure modes across Edge and Cloud

### Out of Scope

- schema redesign
- runtime code changes
- dashboard presentation redesign

## Dependencies

- `WO-IOT-FD-008`
- `WO-IOT-FD-009`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| report becomes too generic | low operational value | anchor every step to actual code paths and tables |
| query pack drifts from schema | stale verification | version with schema changes |
| failure modes stay undocumented | repeated investigation time | include known gap catalog |

## Implementation Plan

1. Define verification steps per session across Edge and Cloud.
2. Add sample SQL or query examples.
3. Create a standard report structure for engineering review.
4. Document expected values and failure signatures.

## Test Plan

### Validation

- walk through one real session using the checklist
- verify query examples return expected rows and fields

### Regression Guardrails

- report must be updated when schema or mapping changes
- checklist must reference real storage locations, not generic placeholders

## Rollback Plan

- no production rollback required
- if the pack is inaccurate, invalidate the version and reissue after engineering review

## Deliverables

- verification checklist
- query pack
- report template

## Acceptance Criteria

- engineers can verify one session metadata flow in a repeatable way

## Evidence Required

- template structure
- query examples
- sample verification walkthrough

## Completion Note

Completed in Batch 1 traceability hardening.

Primary evidence:

- [06-metadata-verification-pack.md](../06-metadata-verification-pack.md)
- [07-local-traceability-runbook.md](../07-local-traceability-runbook.md)
- [query-pack/edge-weighvision-metadata-verification.sql](../query-pack/edge-weighvision-metadata-verification.sql)
- [query-pack/cloud-weighvision-metadata-verification.sql](../query-pack/cloud-weighvision-metadata-verification.sql)
