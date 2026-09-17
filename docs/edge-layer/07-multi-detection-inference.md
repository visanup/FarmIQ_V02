# Per-detection weight inference — 2026-09-15

**Latest state:** Explicit per-object simulation is now enabled at the user’s request. Live jobs complete and persist labelled simulated results. See [simulation mode](08-simulated-object-model.md). The missing-model failures below describe verification before simulation was added.

## Backup before changes

Directory: `/home/qi67/farmiq-update-backup/2026-09-15-152306-before-multi-detection`

- `source-before.tar.gz`: 9,090,738,896 bytes, 5,393 archive entries verified.
- `current-images-backup.tar`: 25,809,850,368 bytes, 50 distinct running/stopped FarmIQ image IDs, 916 archive entries verified.
- Both archives have SHA-256 sidecars. Container inventory, image ID/reference mapping and Git revision/status are saved alongside them.
- Source includes the working tree, including uncommitted files and configuration. Git internals, node_modules, virtual environments and Python caches are excluded. This is a code/image backup, not a consistent database-volume backup.
- An initial source archive attempt encountered a disappearing temporary Git pack. The archive was recreated successfully with Git internals excluded before any application code changes.

## Implemented behavior

For session-backed jobs, inference waits up to 10 metadata fetch attempts, one second apart, for capture metadata. A job with `media_id` selects a capture containing that media ID; it never uses an unrelated latest capture.

Each object in `rawMetadata.detections` supplies its own area, confidence, depth, height, width and length. Capture-level floor depth, ROI count and actual detection count remain context features. A declared detection count that differs from the array length fails validation. Empty arrays generate zero results.

Each successful object produces one `inference_results` row and an outbox event containing:

- the common session ID and capture ID;
- zero-based `detection_index` and actual `detection_count`;
- the original detection, including bbox and measurement fields;
- predicted weight, model provenance and the actual model features used.

Result IDs are deterministic UUIDs derived from tenant, session, capture, detection index and model/package identity. Repeated jobs from multiple uploaded views of the same capture reuse the same IDs; the existing DB/outbox conflict handling prevents duplicate rows. A new capture or model identity yields different results.

Session outcome validation and Cloud sync envelopes preserve detection identity. The existing Cloud consumer stores the entire event payload in its inference result JSON. Existing session `inferenceResultId` and job `result_id` remain single-result pointers (the last processed result); use job `result_ids` or the inference results endpoint to obtain every object. Multiple captures or model versions may therefore have more than one batch of results in a session.

Per-object jobs require a usable model and its required input features. They fail instead of substituting the legacy image-size-based stub. Inference of all objects completes before DB writes start, so a model failure does not save a partly predicted batch. Persistence/outbox writes still use the existing individual operations; DB/network failure can leave partial persistence, and retries use stable IDs.

No historical predictions were backfilled. No trained model was created or selected. Using an existing model per object does not validate its accuracy: the training target and calibration must support individual-object weights, especially if earlier training labels represented total scale weight.

## Verification

- Python inference/job/DB regression and new per-object tests: **25 passed**, zero skipped, run in an isolated `/tmp` copy.
- Session metadata and controller tests: **6 passed**.
- Session TypeScript compilation: `tsc --noEmit` passed.
- Isolated replay of actual Edge metadata from **2026-09-15 15:00:00 exclusive to 15:18:03.737 inclusive, Asia/Bangkok**: **39 sessions, 220 detections, 220 unique result IDs and outbox IDs**.
- Replaying two views per capture made 440 prediction/save calls while retaining 220 unique identities.
- Replay used a deterministic test model and mocked DB/outbox; it validates object mapping and deduplication, not weight accuracy or production persistence. See `evidence/multi-detection-replay-2026-09-15.json`.

## Running environment at completion

The existing development containers bind-mount source and automatically reload. After the tested files were installed, both `farmiq-edge-vision-inference` and `farmiq-edge-weighvision-session` were healthy. Inference had previously failed startup on a temporary database DNS resolution error; after reload it connected successfully.

`POST /api/v1/inference/models/refresh` still returned `status: stub_mode`, no package and no active model path. Service logs reported no effective subscription cached for `tenant-batch5-e2e` / `site-batch5-e2e`.

**Production per-object weights remain unavailable until a suitable model subscription is configured and activated.** New per-object jobs report a failure in this state; they do not store invented stub weights.

## Rollback

1. Verify the SHA-256 sidecars in the backup directory.
2. Extract only the affected application source files from `source-before.tar.gz` to a temporary directory, then restore them to the checkout. Avoid restoring the entire working tree over newer work or live data.
3. Source files affected: inference `app/job_service.py`, `app/inference_service.py`; session `src/controllers/sessionController.ts`, `src/services/sessionService.ts`, `src/utils/weighvisionMetadata.ts`. Test changes are independent of runtime rollback.
4. If image rollback is needed, load `current-images-backup.tar`. Use `images-before.json` and `containers-before.json` to restore image references/tags to their saved IDs. The archive was saved by immutable image IDs.
5. Reload/recreate only the affected services using their existing compose configuration, and check health and model activation. No DB schema migration was introduced by this change.

## Docker rebuild and live API verification

Both services were rebuilt using `docker compose -f docker-compose.yml -f docker-compose.dev.yml build edge-vision-inference edge-weighvision-session`, then recreated with `up -d --no-deps --force-recreate` for those two services only.

Verified running images:

- Inference: `sha256:b76a82e5f99fde8cb0e454e4dd5d9c989862461a8041032902dabc643b3a6c4f`
- Session: `sha256:386faf5f653b0fb3368b1cc03303c777f3430595bedb16ecf7ac971f12a85156`

Both containers are running and healthy. Testing the images directly without source bind mounts passed: session tests 6/6 and TypeScript typecheck; inference replay 39 sessions / 220 unique object results using a test model and mocked persistence in a network-isolated container.

A live API job for real session `20260915_084542` (6 actual detections, ROI count 6) was accepted and then failed with `Per-object inference requires an active model and valid object features`. Job ID: `ff1986ce-c3ac-425f-ab9b-66d4bde01e7f`. Model refresh still reported `stub_mode`, no active package. The database contained zero inference results for that session before and after the test, confirming no simulated weights were persisted.

Evidence: `evidence/multi-detection-rebuild-test-2026-09-15.json`. Rebuild/deployment/testing is complete; usable individual-object weights still require activating a suitable model subscription.
