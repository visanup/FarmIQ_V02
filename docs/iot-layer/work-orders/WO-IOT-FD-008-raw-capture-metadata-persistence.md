# Work Order: WO-IOT-FD-008 - Raw Capture Metadata Persistence

**Work Order ID**: `WO-IOT-FD-008`  
**Ticket**: `IOT-FD-008`  
**Epic**: `EPIC-IOT-FD-02` Metadata Pipeline Verification  
**Owner Role**: `Node Edge Engineer`  
**Suggested Assignee**: Edge Session and Persistence Engineering  
**Suggested Reviewer**: Lead Software Architect, Data Lead  
**Priority**: P0  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 12-18 hours  
**Execution Model**: schema and service change with idempotency review

---

## Objective

Persist full raw capture metadata on the Edge for audit, replay, and downstream Edge-to-Cloud feature extraction.

## Business Outcome

This creates the durable audit layer required before normalized feature storage, Edge-to-Cloud synchronization, and Cloud AI-readiness work can be trusted.

## Agent Skill Profile

### Primary

- `Node Edge Engineer`

### Supporting

- `Data Engineer`
- `Repo Auditor`

## Code Areas

- `edge-layer/edge-weighvision-session/prisma/schema.prisma`
- `edge-layer/edge-weighvision-session/src/services/sessionService.ts`
- `edge-layer/edge-weighvision-session/src/controllers/sessionController.ts`
- `edge-layer/edge-ingress-gateway/src/ingress/processor.ts`

## Scope

### In Scope

- define raw JSONB storage model
- persist by `session_id`, `media_id`, `tenant_id`, `trace_id`
- ensure idempotent writes
- expose retrieval path or query support

### Out of Scope

- normalized feature table design
- AI model serving
- cloud synchronization redesign beyond the agreed metadata contract

## Dependencies

- `WO-IOT-FD-006`
- `WO-IOT-FD-007`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| raw payload is large | storage growth | define retention and index strategy early |
| duplicate metadata writes | inconsistent audit state | use idempotent key strategy |
| wrong ownership boundary | future refactor cost | decide whether session service or dedicated store owns raw metadata |

## Implementation Plan

1. Define raw metadata ownership and schema.
2. Add migration or table creation logic.
3. Implement persistence path from routed event or API.
4. Add duplicate-safe behavior and retrieval support.
5. Confirm persisted raw metadata can feed the agreed Edge-to-Cloud mapping path.
6. Test storage, lookup, and idempotency behavior.

## Test Plan

### Static Verification

- confirm schema includes tenant, session, media, trace, and raw payload
- confirm service code enforces idempotent key strategy

### Runtime Verification

- store one full payload successfully
- replay the same payload without creating duplicate rows
- retrieve stored raw metadata for audit

### Regression Guardrails

- existing session create, bind, and finalize flows must still pass
- metadata persistence failure must not silently corrupt session state

## Rollback Plan

- revert migration and persistence path if storage design is rejected before rollout
- if deployed in a non-production environment, disable writes and preserve source events for replay

## Deliverables

- schema change
- persistence implementation
- tests for write and idempotency

## Acceptance Criteria

- a full raw metadata payload can be queried for any stored session

## Evidence Required

- migration or schema diff
- sample stored payload
- idempotency test result

## Completion Note

Completed in Batch 1 traceability hardening.

Validated implementation areas:

- `edge-layer/edge-weighvision-session/src/controllers/sessionController.ts`
- `edge-layer/edge-weighvision-session/src/services/sessionService.ts`
- `edge-layer/edge-weighvision-session/src/db/ensureSchema.ts`
- `edge-layer/edge-weighvision-session/src/db/migrate.ts`
- `edge-layer/edge-weighvision-session/prisma/schema.prisma`
