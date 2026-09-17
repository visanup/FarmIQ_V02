# Simulated per-object model

Enabled on 2026-09-15 at the user's request, for testing the multi-detection pipeline before a trained model is available.

## Behavior

- Explicit setting: `SIMULATED_MODEL_ENABLED=true`.
- Application default is false; `docker-compose.dev.yml` enables it by default for the current development stack. The production compose is unchanged.
- Simulation overrides model selection while enabled, so it does not depend on a model subscription.
- Model version: `simulated-geometry-v1`.
- Prediction mode: `simulated_per_object`; result metadata contains `simulated=true`, `stub_mode=true`, and `weight_accuracy_validated=false`.
- Simulation uses each detection's positive `area_xy_mm2`. If unavailable or invalid, it uses a valid bounding-box area in pixels, recording which input was used.
- Test formula: `clamp(object_area / 10000, 0.01, 999)` kg. This arbitrary scaling is not calibrated weight estimation; values must not be interpreted as measured or accurate animal weights.
- Confidence is 0. Original session/capture/detection identities are retained. Missing geometry fails explicitly.
- Existing per-object result IDs prevent duplicate results for repeated views or jobs using the same capture and model.
- Turning simulation off restores the requirement for an active model for per-object jobs.

## Deployment and verification

Only `edge-vision-inference` required further changes and was rebuilt and recreated. Image ID:
`sha256:444b6aa10b33ea928737f87fca440b78dc369b093331eb90bbd746694f5bfb9a`.

- Python regression + simulation tests: **32 passed**.
- Live session: `20260915_084542`, tenant `t-001`, **6 detections**.
- Job: `3944e074-8500-4021-9dea-c88767e1da80`, **completed**.
- Database: **6 separate results**, indices 0–5, all labelled `simulated_per_object` / `simulated=true`.
- Repeating the live job retained **6 results**, no duplicates.
- Outbox: **6 events** matching the results.
- Both inference and session services are healthy.
- These live simulated results were intentionally persisted as part of the requested test. No historical backfill was performed.

Evidence: [live test](evidence/simulated-model-live-test-2026-09-15.json).

## Disable simulation

From `edge-layer`:

```bash
SIMULATED_MODEL_ENABLED=false docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --no-deps --force-recreate edge-vision-inference
```

Persist `SIMULATED_MODEL_ENABLED=false` in the compose environment for subsequent deployments, and activate an appropriate real model. Simulated records use their own model version and are not overwritten by real-model results.

## Backup

Previous changed files are archived at `/home/qi67/farmiq-update-backup/2026-09-15-152306-before-multi-detection/pre-simulation-source.tar.gz` with a SHA-256 sidecar. The previous inference image is retained as `farmiq-rollback/edge-vision-inference:before-simulation-20260915`. The earlier full code/images backup remains in that same directory.
