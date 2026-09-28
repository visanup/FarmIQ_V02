# Weak allocation shadow integration

## Scope and plan

Use the approved 2026-09-19 candidate as an experimental model. All outputs carry
`shadow_only=true`, `individual_accuracy_validated=false`, and
`decision_use_allowed=false`. Standard approval is not accuracy approval.

1. Add an opt-in XGBoost branch to Edge jobs after legacy scalar processing completes.
2. Select the capture linked to the job's media ID; retain the complete raw metadata.
3. Verify a deployment-pinned manifest hash and file hashes before loading joblib.
4. Apply whole-session QC, construct training-compatible features, predict raw scores,
   and normalize scores to the stable scale total.
5. Atomically store session outcome/event and per-detection allocations in PostgreSQL.
6. Exercise mock success, rejection, checksum failure, duplicate processing and failure isolation.
7. Run a local shadow deployment against an isolated database, leaving field deployment
   to the actual Edge machine (this workspace is not the farm machine).

## Behavior and storage

The existing `inference_results` and scalar event path keep their behavior. The new
branch runs as a separate tracked asyncio task, offloading XGBoost work to a thread.
At most eight pending/running shadow tasks are retained and inference is serialized.
Overflow is logged and skipped without delaying or failing the legacy job. This is
best-effort observation, not a durable inference queue; process termination can lose
pending shadow work. Database retries are idempotent for the same tenant/job/model,
not a claim of deduplication across newly created jobs for the same capture.
Model failures return `REJECTED_MODEL_UNAVAILABLE`; invalid input returns
`REJECTED_QUALITY` with no allocations. Shadow errors cannot change completed job status.

`allocation_shadow_events` is a local held outbox containing the versioned
`weighvision.group_allocation.completed` payload, identity, rejection reasons,
manifest checksum, timing, raw sum and reconciliation error.
`session_bird_allocations` contains event/tenant/session/capture/detection/model keys
and raw and allocated grams. Inserts use a transaction and deterministic event ID
per tenant/job/model, so retries do not duplicate rows.

Cloud ingestion does not yet support this event. Therefore its delivery status is
`held_shadow`; it is deliberately not placed in the production sync outbox.
No Cloud UI or downstream automation receives allocation values in this phase.

## Input contract

Session context: tenant/session/capture/media IDs, timestamp, breed, sex, age_days,
image width/height, ROI rectangle. Scale: weight_kg, weight_stable, scale_id,
calibration_version, tare_verified. Each detection: unique detection_index,
area_xy_mm2, width_mm, length_mm, height_mm, depth_mm, confidence, bbox_xyxy,
mask_xy. roi_count must equal the number of detections.

Use elapsed days since 2026-09-09 for the supplied sample: male, age 10 on
2026-09-19. These values exist only in test fixtures; runtime must receive actual
flock context. No deployment-wide guessed defaults are applied.

The session service already returns rawMetadata and mediaIds; this integration
uses them without altering session scalar behavior. Missing context is rejected.
The existing candidate was trained with missing normalized centroids and an outlier
flag fixed to zero. Runtime preserves this definition; changing it requires retraining.
Masks must be within both image and ROI; one rejected bird rejects the entire group.

## Local deployment and rollback

The reproducible Compose project is in `ml_weight_prediction/shadow-integration`.
It uses its own PostgreSQL database and mocks; no real MQTT, camera, scale or Cloud
control-plane endpoint is connected. Build the shadow image, package the existing
candidate with the approved Male workbook, then start the Compose project and run
the integration test inside it. Configuration requires:

- `ALLOCATION_SHADOW_ENABLED=true`
- `ALLOCATION_SHADOW_PACKAGE_DIR` pointing to a read-only approved model package
- `ALLOCATION_SHADOW_MANIFEST_SHA256` pinned from the trusted package at deployment

Set `ALLOCATION_SHADOW_ENABLED=false` and restart to stop allocation while retaining
legacy processing. Do not route the new package through the legacy linear subscription.
Only load trusted joblib files: checksum validation is integrity checking, not a
sandbox for executable deserialization. Database rows are retained for analysis.

## Validation and limits

Required tests: real model loading and inference, stable total reconciliation,
whole-session rejection, missing/duplicate detections, age and ROI rejection,
checksum mismatch, media association, actual PostgreSQL schema/atomicity/idempotency,
and proof that scalar result and job success survive shadow failure.
All mock measurements/calibration IDs must remain marked as fixtures.
This stage validates function, not individual accuracy. A sum equal to scale total
is an imposed allocation constraint, not evidence of accurate individual predictions.

## Reproduce (PowerShell, from cloud-ml-model-service)

```powershell
docker build -f ../../edge-layer/edge-vision-inference/Dockerfile.shadow -t farmiq-allocation-shadow:local ../../edge-layer/edge-vision-inference
. ./ml_weight_prediction/shadow-integration/prepare.ps1
docker compose -f ml_weight_prediction/shadow-integration/compose.yaml up -d --wait
docker compose -f ml_weight_prediction/shadow-integration/compose.yaml exec -T edge python -m pytest tests/test_allocation_shadow.py -q
docker compose -f ml_weight_prediction/shadow-integration/compose.yaml exec -T edge python /smoke/smoke_http.py
docker run --rm -e ALLOCATION_SHADOW_ENABLED=false farmiq-allocation-shadow:local python -m pytest tests/test_db.py tests/test_inference_service.py tests/test_job_service.py -q
```

`prepare.ps1` packages only if the versioned directory is absent, then sets the
manifest pin in the current PowerShell process. Dot-source it again in a new shell.
For farm rollout obtain the expected hash from a trusted release independently;
do not automatically re-trust a modified package. Mount the package read-only.
The mock legacy model intentionally returns 1.23 kg. Mock media is a byte fixture;
this verifies orchestration, not image decoding, camera geometry extraction or scale
hardware calibration. XGBoost receives real features from synthetic detections.

Stop only this local deployment, retaining evidence and its database:

```powershell
. ./ml_weight_prediction/shadow-integration/prepare.ps1
docker compose -f ml_weight_prediction/shadow-integration/compose.yaml stop
```

No host ports are published. No production database or production Docker Compose
project is modified. The image uses Python 3.11 with CPU XGBoost and pinned direct
dependencies; it does not change the normal Edge Dockerfile/requirements.

## Field rollout checklist (not executed on the farm machine)

- Deploy this code and `Dockerfile.shadow` image with existing scalar configuration
  unchanged. Add the trusted allocation package, pinned checksum and opt-in env vars.
- Use real tenant/session/capture/media associations and flock context; never copy
  mock scale IDs, calibration, tare flags, images, age or the 1.23 kg legacy fixture.
- Keep allocation local/held, exclude it from dashboards and decision consumers.
- Observe rejection reasons, queue-full warnings, inference latency, resource usage,
  scalar error rates and database growth. Set site-specific retention before a long run.
- Revert by disabling the allocation flag and restarting. Existing records remain.
- A production decision rollout needs labelled individual weights, independent
  day/flock/camera validation, agreed accuracy thresholds and separate approval.

Completion evidence is recorded in `SHADOW_ALLOCATION_TEST_REPORT.md`.
