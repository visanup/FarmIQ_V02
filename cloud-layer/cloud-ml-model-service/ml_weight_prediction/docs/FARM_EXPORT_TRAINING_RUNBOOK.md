# Farm export weak-training runbook

Use this runbook when FarmIQ exports the same four metadata files:
`session_capture_metadata`, `media_objects`, `weight_sessions`, and
`inference_results`.

This pipeline trains only a weakly supervised group-scale allocation candidate.
It does not validate individual-bird accuracy. Individual regression requires
stable, calibrated `actual_weight_g` labels linked one-to-one to each bird.

## 1. Filter metadata to sampled images

```powershell
$python = "C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python scripts/filter_sampled_export.py `
  --images-dir data/raw/farm_export_images `
  --metadata-dir data/raw/farm_export_metadata/<export-folder> `
  --output-dir data/processed/<export-name>/sampled_export
```

Review `sampled_image_metadata_audit.csv`. Every selected image must have a
media object, capture metadata, and weight session before proceeding.

## 2. Build and audit the training dataset

Set the flock context explicitly. `age-start-date` is the capture date whose
age is known; the script calculates every later capture's age from its date.

```powershell
& $python scripts/run_weak_training_pipeline.py
```

Set the file paths and flock context in `.env` before running. The configured
`Broiler_Performance_Standard_Approved.xlsx` must contain approved daily
standard rows for the configured breed and sex. Command-line
arguments override the matching `.env` value when a one-off run needs a change.

Review `weak_data_audit.csv` and `summary.json`. Do not bypass quality failures
by manually editing the derived CSV. Export more source sessions instead.

## 3. Train only after audit acceptance

Set `WEAK_TRAIN_RUN_TRAIN=true` in `.env`, or add `--train`. The trainer uses session-level,
chronological train/validation/test splits and rejects datasets with fewer than
five independent sessions or fewer than five collection days. The wrapper also
requires at least 100 quality-passing sessions by default. A lower threshold
requires an explicit `--min-eligible-sessions` decision and should be treated
as an experiment, not a production candidate.

The created model must remain labelled `WEAK_ALLOCATION` and be evaluated in
shadow mode. It must not be presented as a validated individual-weight model.

## 4. Test an individual-image prediction against a scale reading

The farm scale has a **100 g display resolution**. Record
`scale_resolution_g=100` with every test run. A reading of `300 g` is a
displayed value, not a claim that the true weight is exactly `300.0 g`.

Use a scale reading as an individual-bird test label only after visually
confirming that exactly one chicken occupies the weighing ROI/platform. A
detector reporting `detection_count=1` alone is not sufficient: it may have
missed a chicken. Chickens outside the weighing ROI do not invalidate the
label.

For each accepted test capture, record the image/session ID, stable displayed
weight, visual prediction, detector count, visual single-bird confirmation, and
the scale resolution. Report both of the following:

| Measure | Calculation | Purpose |
| --- | --- | --- |
| Display error | `predicted_weight_g - displayed_scale_weight_g` | Shows the difference from the value displayed by the scale. |
| Resolution-aware absolute error | `max(0, abs(display_error_g) - 50)` | Removes the unavoidable ±50 g uncertainty only when the scale rounds to the nearest 100 g. |

Also report the percentage of accepted captures with absolute display error at
most `100 g` (one scale step). Keep the ordinary MAE and MAPE as well; do not
present a sub-100 g result as more precise than the scale allows.

Before using the ±50 g interval, confirm whether the scale rounds to nearest,
always floors, or always ceils its display. If its rounding rule is unknown,
report display error and the ±100 g one-step rate only.
