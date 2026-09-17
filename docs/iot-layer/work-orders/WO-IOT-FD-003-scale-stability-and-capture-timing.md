# Work Order: WO-IOT-FD-003 - Scale Stability and Capture Timing

**Work Order ID**: `WO-IOT-FD-003`  
**Ticket**: `IOT-FD-003`  
**Epic**: `EPIC-IOT-FD-01` Weight Estimation Validation  
**Owner Role**: `Python CV Engineer`  
**Suggested Assignee**: IoT Capture Engineering  
**Suggested Reviewer**: Lead Software Architect, QA Benchmark Lead  
**Priority**: P0  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 10-14 hours  
**Execution Model**: primary engineer with data and QA support

---

## Objective

Validate whether unstable or mistimed load-cell readings are contributing to field overestimation.

## Business Outcome

If scale timing is part of the defect, the team needs an approved stable-capture rule before any model upgrade or AI effort proceeds.

## Agent Skill Profile

### Primary

- `Python CV Engineer`

### Supporting

- `Data Engineer`
- `QA Benchmark Agent`

## Code Areas

- `iot-layer/weight-vision-capture/run_service.py`
- `iot-layer/weight-vision-capture/data/metadata/*.json`
- scale-related metadata fields including `scale.weight_kg` and `weight_source`

## Scope

### In Scope

- inspect stable-window logic
- compare raw scale samples and captured weights
- assess timestamp alignment between image and weight capture
- recommend field-safe stability parameters

### Out of Scope

- ingress routing changes
- feature store design
- model benchmarking

## Dependencies

- `WO-IOT-FD-001`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| raw sample history may be incomplete | cannot prove timing issue | document data gaps explicitly |
| capture metadata may only expose summarized weight | limits analysis depth | compare code logic with stored output shape |
| parameter change may reduce throughput | operational side effect | validate recommendation against field cadence |

## Implementation Plan

1. Document the current stable-window and post-capture rules.
2. Compare captured weight against available scale timing evidence.
3. Assess whether image and scale timestamps drift materially.
4. Define recommended stability parameters and operational caveats.

## Test Plan

### Static Verification

- confirm scale capture branches in `run_service.py`
- confirm metadata fields used in analysis are actually emitted

### Data Verification

- evaluate abnormal and normal sessions
- compare captured values with field timing evidence

### Regression Guardrails

- recommended settings must be justified by observed sessions
- any parameter proposal must include operational tradeoff notes

## Rollback Plan

- no production rollback required for analysis-only work
- if a proposed parameter baseline proves unsafe, revert to previous capture settings and archive the recommendation

## Deliverables

- timing analysis report
- stable-window recommendation
- impacted-session list

## Acceptance Criteria

- stable capture rules are documented
- the team can determine whether timing instability contributed to abnormal sessions

## Evidence Required

- sample session timing comparison
- rule recommendation with rationale

## Completion Note

Completed in Batch 2 investigation.

Primary evidence:

- [08-weight-estimation-audit-pack.md](../08-weight-estimation-audit-pack.md)
- `docs/iot-layer/evidence/batch2-weight-audit-summary.json`
- `iot-layer/weight-vision-capture/run_service.py`

Completion summary:

- confirmed `21 / 129` captures missing scale weight
- confirmed `15 / 129` captures tagged `weight_source = unstable`
- recommended tighter stable-window and post-capture timing baseline for the next controlled rerun

Residual note:

- direct raw serial-line evidence is still required on a live bench to close the suspected unit-mismatch cause conclusively
