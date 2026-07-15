# Work Order: WO-IOT-FD-012 - YOLO12 vs YOLO26 Benchmark

**Work Order ID**: `WO-IOT-FD-012`  
**Ticket**: `IOT-FD-012`  
**Epic**: `EPIC-IOT-FD-03` YOLO26 Model Upgrade  
**Owner Role**: `QA Benchmark Agent`  
**Suggested Assignee**: CV Benchmark and QA Engineering  
**Suggested Reviewer**: Lead Software Architect, Product Owner for WeighVision  
**Priority**: P1  
**Status**: Completed  
**Created**: 2026-07-13  
**Completed**: 2026-07-14  
**Estimated Effort**: 12-18 hours  
**Execution Model**: benchmark harness with reproducible evidence

---

## Objective

Benchmark YOLO12 and YOLO26 on the same field evaluation dataset and produce a rollout-ready comparison.

## Business Outcome

This provides the evidence required to justify or reject the model upgrade on both quality and runtime cost.

## Agent Skill Profile

### Primary

- `QA Benchmark Agent`

### Supporting

- `Python CV Engineer`
- `Documentation Agent`

## Code Areas

- IoT capture CV pipeline
- evaluation dataset and benchmark scripts
- `iot-layer/weight-vision-train-model-yolo26`

## Scope

### In Scope

- freeze the evaluation dataset
- compare runtime and quality metrics
- compare downstream feature impact
- document reproducible benchmark commands

### Out of Scope

- production rollout
- capture parameter redesign outside benchmark context
- AI weight model training

## Dependencies

- `WO-IOT-FD-001`
- `WO-IOT-FD-011`

## Risks and Controls

| Risk | Impact | Control |
| --- | --- | --- |
| benchmark dataset shifts between runs | invalid comparison | freeze dataset before execution |
| settings differ between models | unfair result | standardize thresholds and evaluation protocol |
| only speed or only quality is measured | weak decision basis | require both runtime and quality metrics |

## Implementation Plan

1. Freeze the evaluation dataset and record its source.
2. Define metric set and execution conditions.
3. Run YOLO12 and YOLO26 with consistent settings.
4. Compare runtime, memory, and quality.
5. Publish benchmark report and recommendation.

## Test Plan

### Benchmark Verification

- verify both models run against the same dataset
- verify metrics are collected with the same procedure

### Regression Guardrails

- results must be reproducible from recorded commands
- recommendation must document known blind spots

## Rollback Plan

- if benchmark quality is insufficient, reject YOLO26 promotion and retain YOLO12
- preserve benchmark artifacts for future reevaluation

## Deliverables

- benchmark harness or command set
- model comparison report
- rollout recommendation

## Completion Summary

- benchmark harness implemented in `iot-layer/weight-vision-capture/benchmark_yolo_models.py`
- harness freezes a reproducible subset and evaluates both models on the same `16` frozen `test` images
- local candidate `yolo26_candidate_local` materially outperformed the current baseline in segmentation quality and average latency
- benchmark comparison was executed against the direct training-workspace candidate artifact; after benchmark completion, the same candidate was promoted into `camera-config/model/best.pt` for runtime use
- benchmark evidence stored in:
  - `docs/iot-layer/evidence/batch3-yolo26-benchmark/benchmark-report.json`
  - `docs/iot-layer/evidence/batch3-yolo26-benchmark/benchmark-summary.md`

## Acceptance Criteria

- both models are compared on the same dataset and metric set

## Evidence Required

- dataset freeze note
- metric table
- recommendation summary
- `docs/iot-layer/10-yolo26-upgrade-pack.md`
- `docs/iot-layer/evidence/batch3-yolo26-benchmark/benchmark-summary.md`
