# Work Order: WO-IOT-FD-005 - Parameter Baseline Validation Report

**Work Order ID**: `WO-IOT-FD-005`  
**Ticket**: `IOT-FD-005`  
**Epic**: `EPIC-IOT-FD-01` Weight Estimation Validation  
**Owner Role**: `QA Benchmark Agent`  
**Suggested Assignee**: QA and Benchmark Engineering  
**Suggested Reviewer**: Lead Software Architect, Product Owner for WeighVision  
**Priority**: P1  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 8-12 hours  
**Execution Model**: validation-focused multi-role review

---

## Objective

Publish an approved parameter baseline and validation report after anomaly investigation and tuning work completes.

## Business Outcome

This work order produces the controlled baseline that the team can deploy or treat as the new operating reference.

## Agent Skill Profile

### Primary

- `QA Benchmark Agent`

### Supporting

- `Python CV Engineer`
- `Documentation Agent`

## Code Areas

- candidate capture parameters in `iot-layer/weight-vision-capture/run_service.py`
- evidence from the validation dataset and audit extracts
- relevant docs in `docs/iot-layer`

## Scope

### In Scope

- consolidate tuning outcomes
- validate before and after results
- freeze approved parameter set
- document residual risk and rollout recommendation

### Out of Scope

- new schema design
- new model rollout
- dashboard changes

## Dependencies

- `WO-IOT-FD-002`
- `WO-IOT-FD-003`
- `WO-IOT-FD-004`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| validation sample too small | false confidence | require representative anomalous and normal samples |
| multiple changes move at once | cannot attribute benefit | document exact parameter delta |
| benchmark result is not field-aligned | poor rollout choice | include field-oriented evidence summary |

## Implementation Plan

1. Gather recommended settings from completed investigation work.
2. Replay or re-evaluate validation sessions.
3. Compare baseline vs candidate results.
4. Publish approval-ready report and residual risk note.

## Test Plan

### Verification

- compare old and new parameters on the same validation set
- verify metric definitions are stable between runs

### Regression Guardrails

- report must record exact parameter delta
- report must note unresolved risks explicitly

## Rollback Plan

- if candidate baseline is rejected, retain previous operating parameters
- archive rejected parameter sets and the reasons for rejection

## Deliverables

- approved parameter baseline
- before and after validation report
- residual risk note

## Acceptance Criteria

- corrected settings show measurable improvement on the validation dataset

## Evidence Required

- parameter table
- benchmark comparison
- sign-off recommendation

## Completion Note

Completed in Batch 2 investigation.

Primary evidence:

- [08-weight-estimation-audit-pack.md](../08-weight-estimation-audit-pack.md)
- `docs/iot-layer/evidence/batch2-weight-audit-summary.json`
- [09-final-weight-local-smoke-runbook.md](../09-final-weight-local-smoke-runbook.md)

Completion summary:

- published the recommended baseline for confidence threshold, stable-window duration, post-capture window, new-track delay, scene-change threshold, and focus threshold
- paired the baseline with finalize-path guardrails so `final_weight_kg` survives the finalized event path

Residual note:

- the baseline is validated at repository audit level and local finalized-path proof level; field-side live benchmark validation is still the next operational step
