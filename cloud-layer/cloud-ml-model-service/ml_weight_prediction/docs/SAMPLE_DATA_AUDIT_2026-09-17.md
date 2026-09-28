# Audit: `docs/sample_data` (2026-09-17)

## Result

This is **shadow/inference telemetry**, not an individual-weight training set.
It must not be used as the label source for XGBoost training or for reporting
model accuracy.

## Inventory

| Source | Rows | Sessions | Time range (UTC) |
|---|---:|---:|---|
| `tb_media_objects.csv` | 442 | 221 | 04:00:19--06:28:04 |
| `tb_inference_results.csv` | 938 | 221 | 04:00:21--06:28:07 |

All 938 inference records join to a media object. There are two media objects
per session on average but inference references 221 unique media IDs; determine
whether the other image is the second stereo view, a retry, or an unprocessed
capture before using media completeness as an operational metric.

## Label and model provenance gate

Every inference row has:

- `model_version=simulated-geometry-v1`
- `metadata.simulated=true` and `metadata.stub_mode=true`
- `metadata.prediction_mode=simulated_per_object`
- `metadata.weight_accuracy_validated=false`
- a declared formula: `clamp(object_area / 10000, 0.01, 999) kg; arbitrary test scaling`

There is no `actual_weight_g`, stable-scale flag, individual label type, or
reference scale identifier. `predicted_weight_kg` is generated output, never a
target label. `record_id` is populated but it identifies the inference event,
not a verified bird-to-scale label linkage.

## Feature quality findings

| Field in metadata features | P05 | Median | P95 | Invalid/extreme signal |
|---|---:|---:|---:|---|
| `selected_area_mm2` | 6,549 | 7,670 | 15,059 | maximum 7,455,081; 21 rows > 50,000 |
| `selected_length_mm` | 93.1 | 115.3 | 171.3 | maximum 3,371.8 |
| `selected_width_mm` | 68.9 | 84.3 | 123.1 | maximum 2,980.1 |
| `selected_height_mm` | -353.9 | 35.6 | 70.2 | minimum -28,751.0; 390 rows < 25 |
| `selected_depth_mm` | 944.8 | 979.1 | 1,368.9 | maximum 29,766.0 |
| `selected_confidence` | 0.821 | 0.922 | 0.956 | all 938 are >= 0.80 |

The confidence gate alone therefore accepts severe geometry failures. In
particular, event `bc8f3a91-02ae-511b-a9cb-01eb6b4df46e` has 7,455,081 mm² area,
-28,751 mm height, and yields 745.51 kg under the deliberately arbitrary
simulation formula. This is useful negative/QC evidence, but is not a valid
chicken prediction.

## Required corrective actions

1. Export a reference-scale table with `record_id`/track linkage,
   `actual_weight_g`, `weight_stable`, `weight_label_type=individual`, scale ID,
   and scale calibration status.
2. Add image width/height, ROI clipping, depth-validity, and camera calibration
   version to capture metadata.
3. Reject non-positive height and impossible physical geometry before any weight
   computation. Calibrate exact upper/lower QC bounds from verified labelled
   captures, not from this simulated dataset.
4. Keep this dataset for pipeline, logging, and rejection-path tests. Do not use
   it for fitting, validation metrics, or model promotion.
