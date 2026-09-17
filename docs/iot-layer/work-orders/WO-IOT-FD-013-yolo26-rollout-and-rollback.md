# Work Order: WO-IOT-FD-013 - YOLO26 Rollout and Rollback

**Work Order ID**: `WO-IOT-FD-013`  
**Ticket**: `IOT-FD-013`  
**Epic**: `EPIC-IOT-FD-03` YOLO26 Model Upgrade  
**Owner Role**: `Node Edge Engineer`  
**Suggested Assignee**: Edge Deployment and Runtime Engineering  
**Suggested Reviewer**: Lead Software Architect, Operations Reviewer  
**Priority**: P1  
**Status**: Completed  
**Created**: 2026-07-13  
**Completed**: 2026-07-14  
**Estimated Effort**: 8-12 hours  
**Execution Model**: controlled rollout planning with ops review

---

## Objective

Add deployment controls so YOLO26 can be rolled out and rolled back safely.

## Business Outcome

This work order ensures the model upgrade is operationally reversible and does not require ad hoc field patching.

## Agent Skill Profile

### Primary

- `Node Edge Engineer`

### Supporting

- `Python CV Engineer`
- `Documentation Agent`

## Code Areas

- model selection configuration in IoT capture runtime
- deployment and runtime docs under `docs/iot-layer`
- environment and config examples tied to capture services

## Scope

### In Scope

- model selection switch
- threshold and default config management
- rollback instructions
- release checklist for safe promotion

### Out of Scope

- benchmarking itself
- retraining the model
- cloud-side AI pipeline

## Dependencies

- `WO-IOT-FD-011`
- `WO-IOT-FD-012`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| config switch is too implicit | operator error | define explicit model identifier and default |
| rollback requires code edits | unsafe field recovery | require config-based rollback path |
| threshold mismatch after swap | degraded results | record per-model threshold defaults |

## Implementation Plan

1. Define runtime config switch for model selection.
2. Record per-model threshold and compatibility settings.
3. Document rollout checklist and validation steps.
4. Document rollback procedure with verification steps.

## Test Plan

### Configuration Verification

- verify the runtime can resolve both active and fallback model settings
- verify invalid config fails safely

### Operational Verification

- verify model swap instructions are deterministic
- verify rollback instructions restore the prior state cleanly

### Regression Guardrails

- no rollout without benchmark reference
- no rollback path that depends on source patching in the field

## Rollback Plan

- rollback is the subject of this work order
- required baseline: restore previous model selection and thresholds via config only

## Deliverables

- config change proposal or implementation
- rollback runbook
- release checklist

## Completion Summary

- runtime-config based model selection implemented in `iot-layer/camera-config/model/runtime-config.yaml`
- `active_model` and `fallback_model` controls are now explicit
- `run_service.py` now falls back to the configured baseline profile if active-model initialization fails
- `camera-config/model/best.pt` was overwritten with the promoted YOLO26 candidate while the previous deployed file was preserved as `best.yolo12-backup-20260714.pt`
- the active runtime path now resolves the promoted YOLO26 artifact from `camera-config/model/best.pt`; direct reads from the training workspace are no longer required for normal capture runtime
- a compose overlay and smoke-specific Dockerfile were added so `weight-vision-capture` image rebuild proof can run without touching the production capture profile
- rollout and rollback steps published in `docs/iot-layer/10-yolo26-upgrade-pack.md`

## Acceptance Criteria

- operations can switch model versions without ad hoc patching

## Evidence Required

- config diff
- rollback procedure
- validation checklist
- `docs/iot-layer/10-yolo26-upgrade-pack.md`
- `docs/iot-layer/evidence/batch3-yolo26-runtime-compat.json`
- `docs/iot-layer/evidence/batch3-yolo26-container-smoke.json`
