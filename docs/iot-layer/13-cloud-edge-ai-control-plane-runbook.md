Purpose: Provide a repeatable local runbook for Batch 4 and Batch 5 Cloud-Edge AI control-plane rebuild, startup, and smoke verification.
Scope: `WO-IOT-FD-014` through `WO-IOT-FD-020`, focused on rerunning the verified local Cloud-Edge shadow path and the final Cloud readmodel proof without rediscovering prior defects.
Owner: FarmIQ Edge and Cloud Architecture
Last updated: 2026-07-15

---

## Goal

Use this runbook when you need to rerun Batch 4 locally and prove the full path:

- Cloud dataset contract
- baseline training
- package publish
- site subscription resolve
- Edge cache refresh
- local shadow inference
- result readback with package metadata
- Cloud readmodel session proof with finalized truth and independent shadow prediction

Exit condition:

- `scripts/batch4-container-smoke.ps1` completes successfully
- `scripts/batch5-e2e-smoke.ps1` completes successfully
- `scripts/iot-origin-e2e-html-report.ps1` completes successfully
- smoke result returns `prediction_mode = shadow`
- smoke result returns the same `package_id` through train, subscription cache, and inference result
- Batch 5 session result returns `final_weight_kg = 3.33` and a non-null shadow prediction on the same session
- IoT-origin HTML evidence is produced from a real `weight-vision-service` one-shot run

---

## Files used by this run

- `cloud-layer/docker-compose.yml`
- `cloud-layer/docker-compose.batch4-smoke.yml`
- `cloud-layer/docker-compose.batch5-e2e.yml`
- `edge-layer/docker-compose.yml`
- `edge-layer/docker-compose.dev.yml`
- `edge-layer/docker-compose.batch4-smoke.yml`
- `edge-layer/docker-compose.batch5-e2e.yml`
- `scripts/batch4-container-smoke.ps1`
- `scripts/batch5-e2e-smoke.ps1`
- `scripts/iot-origin-e2e-html-report.ps1`
- `scripts/export-iot-origin-session-report.ps1`

Key documents:

- [12-cloud-edge-ai-control-plane-pack.md](./12-cloud-edge-ai-control-plane-pack.md)
- [batch4-control-plane-verification-2026-07-14.md](./evidence/batch4-control-plane-verification-2026-07-14.md)
- [batch5-e2e-smoke-2026-07-14.md](./evidence/batch5-e2e-smoke-2026-07-14.md)
- [iot-origin-e2e-20260715-095521.html](./evidence/iot-origin-e2e-20260715-095521.html)
- [weighvision-model-control-plane.contract.md](../contracts/weighvision-model-control-plane.contract.md)

---

## Preflight

Before rerunning, verify:

- Docker Desktop is running
- ports `5125`, `5135`, `5107`, `5109` are available to the local stack
- `host.docker.internal` is reachable from containers
- the dataset file exists:
  - `docs/iot-layer/evidence/batch2-weight-audit-dataset.csv`
- the artifact output directory exists or can be created:
  - `cloud-layer/cloud-ml-model-service/artifacts/weighvision`

Recommended cleanup check:

```powershell
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch4-smoke.yml ps
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch4-smoke.yml ps
```

If an old stack is running, reuse it or recreate only the service you changed. Do not delete persistent data unless you are intentionally resetting the smoke environment.

---

## Step 1: Build and start Cloud services

Run from repository root:

```powershell
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch4-smoke.yml up -d --build postgres rabbitmq cloud-identity-access cloud-tenant-registry cloud-ml-model-service cloud-api-gateway-bff
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch5-e2e.yml up -d --build postgres rabbitmq cloud-identity-access cloud-tenant-registry cloud-ml-model-service cloud-ingestion cloud-weighvision-readmodel cloud-api-gateway-bff
```

Expected checks:

- `cloud-ml-model-service` becomes healthy
- `cloud-api-gateway-bff` is running
- `cloud-ingestion` is running for Edge sync-back
- `cloud-weighvision-readmodel` is running for final session verification

Quick verification:

```powershell
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch4-smoke.yml ps
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch5-e2e.yml ps
```

---

## Step 2: Build and start Edge services

Run from repository root:

```powershell
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch4-smoke.yml up -d --build postgres minio edge-media-store edge-weighvision-session edge-policy-sync edge-vision-inference
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch5-e2e.yml up -d --build postgres minio edge-media-store edge-weighvision-session edge-policy-sync edge-sync-forwarder edge-vision-inference
```

Expected checks:

- `edge-policy-sync` is running
- `edge-vision-inference` is running
- `edge-sync-forwarder` is healthy
- `edge-media-store` is healthy
- `edge-weighvision-session` is running

Quick verification:

```powershell
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch4-smoke.yml ps
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch5-e2e.yml ps
```

---

## Step 3: Run unit tests before smoke

Cloud ML:

```powershell
python -m pytest cloud-layer/cloud-ml-model-service/tests/test_api.py -o cache_dir=D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\.tmp_pytest_cloud
```

Edge inference:

```powershell
python -m pytest edge-layer/edge-vision-inference/tests/test_inference_service.py edge-layer/edge-vision-inference/tests/test_job_service.py edge-layer/edge-vision-inference/tests/test_db.py -o cache_dir=D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\.tmp_pytest_edge
```

Cloud BFF:

```powershell
npx jest --runInBand --coverage=false tests/services/weighvisionService.spec.ts tests/controllers/weighvisionController.spec.ts
```

Expected result:

- Cloud: `5 passed`
- Edge: `13 passed`
- BFF header-propagation tests: `4 passed`

Notes:

- Windows may emit `PytestCacheWarning` for temp cache directories; this is non-blocking if tests pass

---

## Step 4: Run Batch 4 smoke

```powershell
powershell -ExecutionPolicy Bypass -File scripts\batch4-container-smoke.ps1
```

The script performs:

- dataset-contract fetch
- train-baseline request
- site subscription publish
- policy-sync wait and cache check
- Edge model refresh
- mock session creation
- mock media upload
- mock capture metadata attach
- inference job submit and polling
- inference result fetch and summary output

## Step 5: Run Batch 5 end-to-end smoke

```powershell
powershell -ExecutionPolicy Bypass -File scripts\batch5-e2e-smoke.ps1
```

The Batch 5 script performs:

- dataset-contract fetch
- baseline package train and publish
- site subscription publish
- policy-sync wait and package resolve check
- Edge model refresh
- mock session creation with UUID outbox event IDs
- mock media upload and bind
- mock capture metadata persistence
- local inference job submit and polling
- session finalize with truth `3.33`
- sync-forward trigger
- Cloud session verification for both finalized truth and shadow prediction
- Edge outbox verification for `acked` prediction event

---

## Step 6: Verify smoke output

The smoke is successful when the returned JSON contains all of the following:

- `dataset_contract_version = 1.0.0`
- `trained_package_id` is not empty
- `policy_cache_package_id == trained_package_id`
- `model_refresh.status = ready`
- `model_refresh.activation_source = manifest`
- `inference_result.prediction_mode = shadow`
- `inference_result.activation_source = manifest`
- `inference_result.package_id == trained_package_id`
- `inference_result.package_version = wv-shadow-docker-smoke-2026.07.14`
- `inference_result.stub_mode = false`

If those fields are present, the local Cloud-Edge control plane is functioning as intended.

Batch 5 is successful when the returned JSON also contains all of the following:

- `final_weight_kg_truth = 3.33`
- `shadow_prediction.prediction_mode = shadow`
- `shadow_prediction.predicted_weight_kg` is non-null
- `shadow_prediction.predicted_weight_kg != final_weight_kg_truth`
- `shadow_prediction.package_id == trained_package_id`
- `sync_outbox_prediction_event.status = acked`

For the IoT-origin HTML report run, success additionally means:

- `ingress.processed_delta >= 1`
- `edge.capture_metadata.source_event_type = weighvision.inference.completed`
- `cloud.finalized_measurement.weight_kg = 3.33`
- `cloud.shadow_prediction.prediction_mode = shadow`
- `cloud.shadow_prediction.predicted_weight_kg != 3.33`
- `artifacts.html_report` and `artifacts.json_report` both exist

---

## Step 7: Run IoT-origin E2E HTML proof

```powershell
powershell -ExecutionPolicy Bypass -File scripts\iot-origin-e2e-html-report.ps1
```

The script performs:

- baseline package train and publish
- site subscription publish and policy-sync verification
- Edge model refresh
- mock capture generation from `iot-layer/weight-vision-capture/data/metadata/20260210_073143.json`
- `weight-vision-service` one-shot execution with local upload override
- Edge session, metadata, and inference verification
- sync-forward trigger
- Cloud finalized-truth and shadow-prediction verification
- HTML and JSON report generation in `docs/iot-layer/evidence/`

If you already have a verified IoT-origin session and only need to regenerate the report:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export-iot-origin-session-report.ps1 `
  -SessionId sess-iot-origin-674d4ad7013244b2bd2a6cb583aef24a `
  -TenantId tenant-batch5-e2e `
  -TruthWeightKg 3.33 `
  -ServiceLogPath docs\iot-layer\evidence\iot-origin-e2e-20260715-095521.log
```

---

## Known defects already handled in code

The following failure classes were already fixed and should not recur unless code regresses:

- container path defaults for Cloud artifact and dataset paths
- Cloud ML healthcheck mismatch between image contents and compose command
- JSON fields from Cloud registry rows returning as strings instead of objects
- BFF internal ML base URL mismatch in Docker
- `edge-policy-sync` request shape mismatch for `tenant_id`, `farm_id`, `barn_id`
- missing `sync_outbox` table bootstrap in `edge-vision-inference`
- inference result `metadata` returned as string instead of object
- Batch 5 producer timestamps missing `Z` and failing Edge session validation
- Batch 5 smoke script using non-UUID outbox event IDs
- Batch 5 smoke script checking `session_id` at the wrong outbox response level
- IoT-origin script using malformed PowerShell interpolation for the Cloud session URL
- IoT-origin script checking deprecated ingress field `stats.processed_count` instead of `counters.messages_valid_total`
- `weight-vision-service` one-shot path inheriting field `.env` upload host and workstation proxy settings during local smoke
- `weight-vision-service` one-shot path not shutting down MQTT cleanly after processing one metadata file

If one of these reappears, compare current code against:

- `cloud-layer/cloud-ml-model-service/app/config.py`
- `cloud-layer/cloud-ml-model-service/app/routes.py`
- `cloud-layer/cloud-api-gateway-bff/src/services/dashboardService.ts`
- `edge-layer/edge-policy-sync/src/services/policySyncService.ts`
- `edge-layer/edge-vision-inference/app/db.py`

---

## Troubleshooting checkpoints

### Cloud ML service is unhealthy

Check:

```powershell
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch4-smoke.yml logs --tail=200 cloud-ml-model-service
```

Look for:

- missing dataset path mount
- artifact directory permission or path issues
- failed JSON normalization in package read paths

### Policy sync does not cache a package

Check:

```powershell
Invoke-RestMethod http://localhost:5109/api/v1/edge-config/state
Invoke-RestMethod "http://localhost:5109/api/v1/edge-config/model-subscription/effective?tenantId=tenant-batch4-smoke&siteId=site-batch4-smoke"
```

Look for:

- `last_error`
- missing `x-tenant-id`
- wrong query param naming

### Inference refresh succeeds but result falls back to stub mode

Check:

```powershell
Invoke-RestMethod -Method Post http://localhost:5107/api/v1/inference/models/refresh
```

Look for:

- `status = ready`
- `activation_source = manifest`
- valid `active_model_path`

If `stub_mode = true`, inspect package manifest and extracted model path.

### Smoke result shows null package metadata

This indicates result-read normalization regressed.

Check:

- `edge-layer/edge-vision-inference/app/db.py`
- `edge-layer/edge-vision-inference/tests/test_db.py`

Expected behavior:

- `metadata` is returned to the API layer as an object, not a JSON string

### Batch 5 session never appears in Cloud

Check:

```powershell
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch5-e2e.yml logs --tail=200 edge-sync-forwarder edge-weighvision-session edge-vision-inference
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch5-e2e.yml logs --tail=200 cloud-ingestion cloud-weighvision-readmodel cloud-api-gateway-bff
```

Look for:

- missing forwarded `Authorization` from BFF to readmodel
- invalid non-UUID outbox event IDs
- prediction outcome publish rejected by session validation
- outbox verification query using the wrong `session_id` location

---

## Rerun strategy after code change

If you change only one service:

- rebuild only that service first
- rerun the related unit tests
- rerun `scripts/batch4-container-smoke.ps1`

Examples:

```powershell
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch4-smoke.yml up -d --build cloud-ml-model-service
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch5-e2e.yml up -d --build cloud-api-gateway-bff
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch4-smoke.yml up -d --build edge-policy-sync
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch4-smoke.yml up -d --build edge-vision-inference
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch5-e2e.yml up -d --build edge-vision-inference
```

---

## Closure criteria

You can mark the rerun successful when all of the following are true:

- unit tests pass
- Cloud and Edge stacks are up
- Batch 4 smoke script passes
- Batch 5 smoke script passes
- smoke result shows non-stub shadow inference with matching package metadata
- Batch 5 session proves finalized truth and shadow prediction coexist without override
- no unresolved `last_error` remains in `edge-policy-sync`
