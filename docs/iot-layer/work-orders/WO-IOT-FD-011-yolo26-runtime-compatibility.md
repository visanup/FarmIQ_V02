# Work Order: WO-IOT-FD-011 - YOLO26 Runtime Compatibility

**Work Order ID**: `WO-IOT-FD-011`  
**Ticket**: `IOT-FD-011`  
**Epic**: `EPIC-IOT-FD-03` YOLO26 Model Upgrade  
**Owner Role**: `Python CV Engineer`  
**Suggested Assignee**: IoT Computer Vision Engineering  
**Suggested Reviewer**: Lead Software Architect, CV Technical Reviewer  
**Priority**: P1  
**Status**: Completed  
**Created**: 2026-07-13  
**Completed**: 2026-07-14  
**Estimated Effort**: 10-14 hours  
**Execution Model**: technical spike with rollout review

---

## Objective

Validate that the current capture stack can safely load and use YOLO26-family segmentation models, with the deployable runtime artifact resolved through `camera-config/model/best.pt`.

## Business Outcome

This prevents an unsafe model swap and gives the team a grounded compatibility decision before benchmark or rollout work begins.

## Agent Skill Profile

### Primary

- `Python CV Engineer`

### Supporting

- `QA Benchmark Agent`
- `Architecture Analyst`

## Code Areas

- `iot-layer/weight-vision-capture/run_service.py`
- `iot-layer/weight-vision-capture/yolo_infer.py`
- `iot-layer/weight-vision-train-model-yolo26/README.md`
- `iot-layer/weight-vision-train-model-yolo26/train.py`

## Scope

### In Scope

- confirm dependency compatibility
- validate model loading and segmentation output compatibility
- identify runtime or code changes required for support

### Out of Scope

- final rollout decision
- production deployment
- dashboard visualization

## Dependencies

- `WO-IOT-FD-006`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| YOLO26 output format differs from current adapter assumptions | capture pipeline breakage | validate object contract before code switch |
| runtime dependency mismatch | startup failure | pin required runtime versions explicitly |
| compatibility spike becomes rollout by accident | uncontrolled change | keep this work order spike-only |

## Implementation Plan

1. Confirm required runtime package versions.
2. Validate model loading in the current capture environment.
3. Compare output object expectations with existing capture code.
4. Document required code or config changes.
5. Publish compatibility recommendation and risks.

## Test Plan

### Static Verification

- verify required model and package assumptions
- inspect capture code assumptions around segmentation outputs

### Runtime Verification

- load YOLO26 successfully
- confirm segmentation outputs can be consumed by the current pipeline or identify deltas

### Regression Guardrails

- no production model switch during compatibility-only work
- every claimed incompatibility must reference code or runtime evidence

## Rollback Plan

- if compatibility is not acceptable, retain YOLO12 as the active runtime path
- do not promote benchmark or rollout tasks without compatibility sign-off

## Deliverables

- compatibility spike report
- required code or config change list
- risk register for upgrade

## Completion Summary

- `UltralyticsSegDetector` introduced as the generic runtime wrapper with backward-compatible alias retained for old callers
- runtime profile resolution added through `iot-layer/camera-config/model/runtime-config.yaml`
- compatibility smoke proved that configured YOLO26 profiles load as `segment` models and return mask polygons
- the promoted runtime profile `yolo26_promoted_bestpt` was confirmed to resolve `iot-layer/camera-config/model/best.pt`
- a dedicated container smoke route was added for `weight-vision-capture` so startup proof can run without RTSP or scale hardware
- runtime evidence stored in `docs/iot-layer/evidence/batch3-yolo26-runtime-compat.json`
- container evidence stored in `docs/iot-layer/evidence/batch3-yolo26-container-smoke.json`

## Acceptance Criteria

- model integration risks are known before rollout implementation begins

## Evidence Required

- runtime check notes
- compatibility findings
- fallback strategy
- `docs/iot-layer/10-yolo26-upgrade-pack.md`
- `docs/iot-layer/evidence/batch3-yolo26-runtime-compat.json`
- `docs/iot-layer/evidence/batch3-yolo26-container-smoke.json`
