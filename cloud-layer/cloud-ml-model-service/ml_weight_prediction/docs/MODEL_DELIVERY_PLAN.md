# Individual chicken weight model: delivery gates

## 1. Outcome and pass criteria

The product output is `predicted_weight_g`, `prediction_status`, and a model
version for every accepted individual detection. The initial operating scope is
one approved camera/calibration, farm, breed/sex mix, and age range represented
by the labelled data. Inputs outside that scope must be reported as
`OUT_OF_DISTRIBUTION` or `REJECTED_QUALITY`, not silently treated as reliable.

The following values are proposed *release gates*, subject to farm owner signoff
against the downstream use case. They are intentionally acceptance targets, not
claims about current performance.

| Gate | Candidate requirement | Why |
|---|---:|---|
| Label integrity | 100% of training labels are `individual` and `weight_stable=true` | prevents target leakage/noise |
| Dataset coverage | >= 1,000 labelled birds, >= 5 independent collection days/batches, >= 100 birds in each supported weight band | avoids a single-session model |
| Holdout MAE | <= 50 g | practical point-estimate accuracy target |
| Holdout P95 absolute error | <= 120 g | protects against harmful tail failures |
| Holdout bias | absolute mean error <= 20 g overall and <= 30 g per supported weight band | prevents systematic under/over-estimation |
| Baseline improvement | XGBoost test MAE improves by >= 15% over training-set median baseline | establishes value over a trivial predictor |
| Robustness | no supported batch/camera subgroup has MAE > 1.5x overall MAE | detects hidden deployment weakness |
| Runtime | p95 local prediction latency <= 100 ms on target edge device | keeps it usable in capture flow |

If the intended use is dosing, sale settlement, or another high-impact decision,
the owner must set stricter targets and an explicit manual-review policy before
production. The current metadata cannot be scored against any of these gates.

## 2. Evidence from current sample

The supplied `metadata.txt` has one session (`20260917_020955`) containing four
detections. All four `per_chicken_records` have `weight_label_type=group_total`,
`group_weight_kg=1.0`, and an estimated value of 0.25 kg. They are excluded from
training. The detected feature measurements are positive and confidence ranges
from 0.814 to 0.909, so they may be retained for feature-pipeline testing.

Detection 2 has `height_mm=22.22`, versus 62.45--67.37 mm for detections 1, 3,
and 4. Treat it as a QC investigation: inspect its depth/mask/capture before
using it as an eligible labelled row. It is a signal, not evidence that every
22 mm observation is necessarily invalid.

## 3. Quality and reference-weight protocol

For each label: one bird, stable calibrated scale, synchronized stereo capture,
and an immutable `record_id` or `locked_track_id` linkage. Store the scale raw
reading in grams, stability flag, scale identifier, calibration/check result,
operator/device timestamp, camera ID, batch, age, breed, and sex where known.

Audit rules: reject missing/non-positive dimensions, confidence below 0.80,
missing label, non-individual label, unstable scale, duplicate record ID, and
mask/ROI clipping. Flag (rather than automatically delete) depth/height outliers
using a QC range approved from training-partition analysis, then configure that
range in the data builder and deploy it with the model. Inspect flagged records;
all exclusions must remain in the audit CSV with a reason.

## 4. Features and leakage policy

Use the 15 model features defined in the feature specification: physical
measurements, confidence, volume proxies, body ratio, bbox geometry, mask fill,
normalized centroid, and an outlier flag. `camera_id`, `batch_id`, and `age_days`
are retained for splitting, subgroup reporting, and drift analysis; do not use
them as model features in v1 unless their production availability and generalization
are demonstrated. Never include scale/group weights, estimated weights, IDs,
raw mask coordinates, or calibration constants that do not vary operationally.

The pipeline derives bbox and polygon-mask features deterministically and needs
the capture image width/height to derive normalized centroids. If dimensions are
missing, the row remains auditable but is not eligible for v1 training.

## 5. Train/validation/test design

Split by independent `batch_id` or collection date (never by individual frames).
Use the latest complete days/batches as a locked 20% test set, then reserve the
latest 25% of the remaining groups as validation (approximately 60/20/20).
All frames of the same bird/track must share a partition. Select hyperparameters
only on validation, freeze them, then report test metrics exactly once.

The candidate trainer compares XGBoost with a median-weight baseline, writes
MAE/RMSE/MAPE/P95/bias metrics, and writes subgroup reports. It stops rather than
creating a random split when there are fewer than five independent groups.

## 6. Package and edge runtime

The package contains `model.joblib`, `manifest.json`, `metrics.json`, feature
order, training-data fingerprint, supported input schema/version, and the model
version. Edge inference must validate units and quality gate first, return an
explicit status/reason, write structured prediction events, and preserve the
raw feature values needed for audit. A model package is immutable; promote a new
directory/version rather than overwriting the active one.

## 7. Shadow then production

1. Deploy candidate alongside the current process with decisions disabled.
2. Log model version, features, status, prediction, later matched scale label,
   camera/batch/age, and latency. Retain unmatched events as well.
3. For at least two production batches and >= 200 matched, quality-passing birds,
   recompute the same metrics and subgroup bias. Check rejection rate and input
   drift against training ranges.
4. Enable a limited canary only after all signed gates pass. Keep manual scale
   as source of truth during the canary.
5. Monitor daily. Roll back immediately if data-contract failures exceed 2%,
   quality rejections exceed the agreed baseline by 50%, MAE exceeds 50 g for a
   completed batch, P95 error exceeds 120 g, or a supported subgroup bias exceeds
   30 g. These thresholds require owner confirmation before activation.

## Required before the next stage

1. An export of individual, stable, scale-calibrated labels linked to `record_id`.
2. Image width and height (or calibrated ROI dimensions) in every metadata export.
3. The supported farm/camera/breed/age scope and business tolerance in grams.
4. Target edge hardware/OS, Python availability, and integration message format.
5. A scale calibration SOP and the identity strategy for repeated frames of one bird.
