# Edge-layer integration contract for group-scale allocation

## Purpose

Implementation update (2026-09-21): the first shadow phase is implemented; see
[implementation/runbook](SHADOW_ALLOCATION_IMPLEMENTATION.md) and
[test evidence](SHADOW_ALLOCATION_TEST_REPORT.md). The design below describes
the broader target contract, not the exact deployed input names. The implemented
adapter uses existing `captureMetadata.rawMetadata` with nested `scale.weight_kg`,
`scale.weight_stable`, `scale.calibration_version`, `scale.tare_verified` and
`scale.scale_id`. XGBoost is a separate opt-in branch, not a replacement for the
legacy scalar model. Results live in the inference database and a held local
outbox; Cloud propagation and decision use are not enabled in this phase.

The current edge path emits one scalar `predicted_weight_kg` for a selected
detection. Group-scale allocation requires an array of per-detection outputs
whose total equals a stable scale reading. This document is the implementation
contract between `ml_weight_prediction`, `edge-vision-inference`,
`edge-weighvision-session`, and `shared/contracts`.

## Required schema v1.1 changes

The capture event must retain all ROI-eligible detections, not only the largest
`selected_detection_index`. Each detection must carry its model features and:

```text
detection_index, track_id?, is_inside_roi, overlap_ratio_with_roi,
is_mask_clipped, quality_pass, quality_reasons
```

The session envelope must add `group_total_weight_g`, `weight_stable`,
`scale_id`, `scale_calibration_version`, `scale_tare_verified`, `age_days`,
`breed`, `sex`, image dimensions, and ROI geometry. `scale_weight_kg` may stay
for backwards compatibility, but model features and allocation output use grams.

## Required output event

Add a versioned event/payload (do not overload the existing scalar-only event):

```json
{
  "event_type": "weighvision.group_allocation.completed",
  "session_id": "...",
  "group_total_weight_g": 1350,
  "weight_stable": true,
  "model_version": "...",
  "prediction_mode": "weak_group_allocation",
  "allocations": [
    {"detection_index": 0, "allocated_weight_g": 322.5,
     "prediction_status": "WEAK_ALLOCATION", "quality_reasons": []}
  ]
}
```

Only quality-passing detections appear in `allocations`. Their values must sum
to `group_total_weight_g` within 0.1 g. Failure of scale stability, model load,
or input contract returns a session-level rejection and no allocation values.

## Service changes

| Component | Required change |
|---|---|
| `edge-weighvision-session` | Normalize and persist every detection, not only the selected one; persist session quality/scale metadata and allocation rows. |
| `shared/contracts` | Add the versioned group-allocation schema and strict unit/status enums. Keep scalar `InferenceCompletedPayloadSchema` unchanged during migration. |
| `edge-vision-inference` | Replace JSON linear-coefficient-only runtime with an approved XGBoost/joblib runtime or a compatible exported model format. Call group allocation only after a stable scale total and quality gates pass. |
| Database | Add a `session_bird_allocations` table keyed by session and detection, with model version, raw score, allocated grams, status, reasons, and created timestamp. |
| Observability | Emit model version, package checksum, quality rejection reason, inference latency, raw sum before normalization, and allocation-total reconciliation. |

## Package compatibility gate

The present training package contains `model.joblib`, while the current
`edge-vision-inference` runtime expects a JSON linear model with coefficients.
They are incompatible. Do not activate a joblib package until the runtime has
been changed, dependency-pinned, checksum-verified, and tested on target edge
hardware. A runtime fallback must return `REJECTED_MODEL_UNAVAILABLE`; it must
not emit a synthetic number derived from image file size.

## Rollout order

1. Ship schema v1.1 and database persistence with allocation disabled.
2. Verify all-detection capture records, ROI flags, scale stability, and units.
3. Deploy the runtime adapter and shadow package; log allocations only.
4. Reconcile raw score sums before normalization and collect individual scale
   calibration samples.
5. Enable UI/API display with `WEAK_ALLOCATION` status. Do not use the value for
   settlement, dosing, or individual accuracy claims.
