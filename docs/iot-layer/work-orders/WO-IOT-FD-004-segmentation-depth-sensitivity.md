# Work Order: WO-IOT-FD-004 - Segmentation and Depth Sensitivity

**Work Order ID**: `WO-IOT-FD-004`  
**Ticket**: `IOT-FD-004`  
**Epic**: `EPIC-IOT-FD-01` Weight Estimation Validation  
**Owner Role**: `Python CV Engineer`  
**Suggested Assignee**: IoT Computer Vision Engineering  
**Suggested Reviewer**: Lead Software Architect, QA Benchmark Lead  
**Priority**: P1  
**Status**: Completed  
**Created**: 2026-07-13  
**Estimated Effort**: 12-16 hours  
**Execution Model**: primary engineer with replay and QA support

---

## Objective

Measure how ROI selection, segmentation quality, and depth sampling influence derived shape features and weight-related interpretation.

## Business Outcome

This work isolates whether the weight error is caused by geometric feature quality rather than load-cell behavior.

## Agent Skill Profile

### Primary

- `Python CV Engineer`

### Supporting

- `QA Benchmark Agent`
- `Data Engineer`

## Code Areas

- `iot-layer/weight-vision-capture/run_service.py`
- `iot-layer/weight-vision-capture/yolo_infer.py`
- saved metadata and mask outputs under `iot-layer/weight-vision-capture/data`

## Scope

### In Scope

- compare normal and abnormal sessions
- review mask clipping, multi-object ROI, and point sampling
- test alternate depth aggregation strategies
- propose parameter tuning candidates

### Out of Scope

- persistent schema changes
- dashboard work
- AI model training

## Dependencies

- `WO-IOT-FD-001`
- `WO-IOT-FD-003`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| visual evidence may be subjective | weak conclusion quality | use measurable feature comparisons and overlays |
| multiple ROI behaviors may overlap | hard to isolate cause | test one variable at a time |
| replay environment differs from field | non-transferable result | use stored field artifacts where possible |

## Implementation Plan

1. Select representative normal and abnormal sessions.
2. Review mask quality and object selection behavior.
3. Compare key feature fields across sessions.
4. Evaluate alternate point and depth aggregation strategies.
5. Publish sensitivity matrix and tuning candidates.

## Test Plan

### Static Verification

- confirm the feature fields analyzed are present in metadata
- confirm ROI and mask logic in source code

### Replay Verification

- inspect stored masks and metadata for target sessions
- recompute comparison values where needed

### Regression Guardrails

- every tuning candidate must name the specific failure mode it addresses
- recommendations must separate measured fact from inference

## Rollback Plan

- no production rollback required unless parameter changes are promoted
- if a candidate tuning degrades results, restore previous capture parameters and archive findings

## Deliverables

- sensitivity matrix
- parameter-risk summary
- tuning candidate list

## Acceptance Criteria

- at least one measurable error pattern is linked to a parameter or detection behavior

## Evidence Required

- overlay references
- abnormal vs normal comparison
- parameter impact notes

## Completion Note

Completed in Batch 2 investigation.

Primary evidence:

- [08-weight-estimation-audit-pack.md](../08-weight-estimation-audit-pack.md)
- `docs/iot-layer/evidence/batch2-weight-audit-summary.json`
- `iot-layer/weight-vision-capture/geometry.py`

Completion summary:

- identified `10 / 129` multi-detection captures inside ROI
- identified `43 / 129` low-confidence selections
- identified `10 / 129` depth outliers and `36 / 129` negative or implausible height values

Residual note:

- these findings are sufficient for parameter baselining and feature-risk classification, but still need field replay or live rerun for final tuning confirmation
