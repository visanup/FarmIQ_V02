# Work Order: WO-IOT-FD-007 - Ingress Routing for Inference Metadata

**Work Order ID**: `WO-IOT-FD-007`  
**Ticket**: `IOT-FD-007`  
**Epic**: `EPIC-IOT-FD-02` Metadata Pipeline Verification  
**Owner Role**: `Node Edge Engineer`  
**Suggested Assignee**: Edge Integration Engineering  
**Suggested Reviewer**: Lead Software Architect, Edge Gateway Owner  
**Priority**: P0  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 8-12 hours  
**Execution Model**: code change with gateway and contract review

---

## Objective

Add Edge ingress routing for `weighvision.inference.completed` so metadata-bearing inference events are no longer dropped.

## Business Outcome

This closes a known data-loss gap between IoT event generation, Edge metadata handling, and eventual Cloud feature delivery.

## Agent Skill Profile

### Primary

- `Node Edge Engineer`

### Supporting

- `Architecture Analyst`
- `QA Benchmark Agent`

## Code Areas

- `edge-layer/edge-ingress-gateway/src/ingress/processor.ts`
- `edge-layer/edge-ingress-gateway/tests/ingress/*.spec.ts`
- downstream destination path defined by metadata persistence design
- Edge-to-Cloud propagation path for synchronized metadata/features

## Scope

### In Scope

- add route for `weighvision.inference.completed`
- preserve tenant, trace, and session context
- define destination payload shape
- preserve downstream Cloud synchronization viability
- add route-level tests

### Out of Scope

- long-term feature-store design
- AI model training
- dashboard work

## Dependencies

- `WO-IOT-FD-006`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| route added before payload contract stabilizes | broken downstream consumer | align with canonical schema first |
| event routing introduces duplicate writes | persistence inconsistency | enforce idempotent downstream handling |
| gateway changes break existing weighvision flow | regression in core session flow | add targeted tests for existing routes and new route |

## Implementation Plan

1. Confirm canonical payload contract for inference metadata events.
2. Add routing rule in ingress processor.
3. Choose or implement destination API body shape.
4. Add tests for successful routing and non-drop behavior.
5. Verify existing weighvision routes still behave correctly.

## Test Plan

### Static Verification

- confirm event name and payload fields in source code
- confirm route body keeps tenant and trace context

### Runtime Verification

- verify `weighvision.inference.completed` is accepted and forwarded
- verify unknown events still fail safely

### Regression Guardrails

- existing session routes must remain green
- route addition must be covered by automated ingress tests

## Rollback Plan

- revert gateway routing change if downstream persistence is not ready
- disable the new route path and restore prior behavior only with explicit incident note

## Deliverables

- ingress routing implementation
- route-level tests
- routing decision note

## Acceptance Criteria

- `weighvision.inference.completed` is routed through a supported path
- route behavior is covered by tests

## Evidence Required

- passing route tests
- payload example and destination mapping

## Completion Note

Completed in Batch 1 traceability hardening.

Validated implementation areas:

- `edge-layer/edge-ingress-gateway/src/ingress/processor.ts`
- `edge-layer/edge-ingress-gateway/tests/ingress/processor.spec.ts`
- `edge-layer/edge-ingress-gateway/tests/ingress/batch1-traceability.smoke.spec.ts`
