# Batch 4 Control-Plane and Shadow Inference Verification

Date: 2026-07-14  
Scope: Local verification for Batch 4 Cloud-Edge AI control plane, baseline training, package activation, and shadow sync-back  
Owner: FarmIQ Edge and Cloud Architecture

---

## Verification summary

Batch 4 is implemented and locally verified at five levels:

1. Cloud dataset contract, registry, subscription, and package download API
2. Real baseline training with exported package artifact
3. Edge package activation and local shadow inference execution
4. Edge job-service sync-back payload enrichment
5. Full Docker Compose smoke proof with live `edge-policy-sync`, `edge-vision-inference`, `edge-weighvision-session`, and Cloud services wired together in one run

This verification is sufficient to mark Batch 4 code-complete in this repository and closed at local container smoke level.

---

## Test and build results

### 1. Cloud ML model service API tests

Command:

```powershell
python -m pytest tests/test_api.py -o cache_dir=D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\tmp_pytest_cache_ml
```

Result:

- `5 passed`

Covered behaviors:

- dataset contract available
- bootstrap baseline creates model and package record
- site subscription resolve and acknowledgement flow works
- real train-baseline route exports a package and exposes a downloadable artifact

### 2. Edge vision inference runtime tests

Command:

```powershell
python -m pytest tests/test_inference_service.py -o cache_dir=D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\tmp_pytest_cache_edge
```

Result:

- included in the consolidated `13 passed` result below

Covered behaviors:

- stub inference path still works
- activated package can drive shadow inference
- runtime info exposes active manifest metadata
- fallback manifest metadata remains available

### 3. Edge vision inference and job-service tests

Command:

```powershell
python -m pytest tests/test_inference_service.py tests/test_job_service.py tests/test_db.py -o cache_dir=D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\.tmp_pytest_edge
```

Result:

- `13 passed`

Covered behaviors:

- stub inference path still works
- activated package can drive shadow inference
- runtime info exposes active and fallback manifest metadata
- async job creation and retrieval
- job completion path
- shadow metadata flow into `create_outbox_event`
- processing failure handling
- inference result read paths normalize `JSONB metadata` back to structured objects

### 4. TypeScript builds

Commands:

```powershell
npm run build
```

Services verified:

- `cloud-layer/cloud-api-gateway-bff`
- `edge-layer/edge-policy-sync`
- `cloud-layer/cloud-weighvision-readmodel`

Result:

- all passed

### 5. Docker Compose smoke proof

Commands:

```powershell
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch4-smoke.yml up -d --build postgres rabbitmq cloud-identity-access cloud-tenant-registry cloud-ml-model-service cloud-api-gateway-bff
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch4-smoke.yml up -d --build postgres minio edge-media-store edge-weighvision-session edge-policy-sync edge-vision-inference
powershell -ExecutionPolicy Bypass -File scripts\batch4-container-smoke.ps1
```

Result:

- passed

Observed smoke summary:

- `dataset_contract_version = 1.0.0`
- `trained_package_id = 26c3c4457ad847e4baebd95ee5e9991e`
- `policy_cache_package_id = 26c3c4457ad847e4baebd95ee5e9991e`
- `model_refresh.status = ready`
- `model_refresh.activation_source = manifest`
- `session_id = sess-batch4-smoke-938088a8a174430b9875b2ca76d58ff6`
- `prediction_mode = shadow`
- `activation_source = manifest`
- `predicted_weight_kg = 0.24`
- `package_version = wv-shadow-docker-smoke-2026.07.14`
- `feature_schema_version = 1.0`
- `model_version = wv-shadow-docker-smoke-2026.07.14`
- `package_id = 26c3c4457ad847e4baebd95ee5e9991e`
- `stub_mode = false`

This proves the full path:

- Cloud trains and publishes a package
- Cloud subscription resolves the same package for the target site
- Edge policy-sync caches that package
- Edge inference refresh activates it
- local shadow inference runs on mock session data
- result readback returns the full runtime metadata needed for auditability

---

## Real baseline training evidence

### Dataset used

- `docs/iot-layer/evidence/batch2-weight-audit-dataset.csv`

### Training execution summary

Route exercised:

- `POST /api/v1/ml/weighvision/train-baseline`

Observed output:

- dataset rows: `105`
- training rows: `84`
- validation rows: `21`
- package version: `wv-shadow-field-baseline-2026.07.14`
- runtime family: `python-linear-regression`
- feature schema version: `wv-feature-schema-v1`

Exported artifact:

- `cloud-layer/cloud-ml-model-service/artifacts/weighvision/tenant-batch4-real/wv-shadow-field-baseline-2026.07.14.tar.gz`

Checksum:

- `fd997e81063b79cc8fc0885fae4325c9921ab2b6818fef5e5246d818a00fadbc`

Metrics:

- train `mae_kg = 2.78364`
- train `rmse_kg = 3.57635`
- train `r2 = 0.865122`
- validation `mae_kg = 7.49596`
- validation `rmse_kg = 7.857154`
- validation `r2 = -10.758159`
- naive validation `mae_kg = 2.647279`
- naive validation `rmse_kg = 3.178186`
- naive validation `r2 = -0.923833`

Interpretation:

- the pipeline now produces a real trained package and metrics
- this first linear baseline is not promotion-ready because validation performance is worse than the naive baseline
- the package remains valid for shadow-only plumbing verification

---

## Real package activation and local shadow inference evidence

Artifact source:

- `cloud-layer/cloud-ml-model-service/artifacts/weighvision/tenant-batch4-real/wv-shadow-field-baseline-2026.07.14.tar.gz`

Activation proof:

- package extracted into local Edge runtime cache
- active manifest written to local cache
- `active_model_path` resolved to:
  - `edge-layer/edge-vision-inference/runtime-model-cache-smoke/pkg-field-baseline-20260714/wv-shadow-field-baseline-2026.07.14/model/model.json`

Observed runtime state:

- `status = ready`
- `activation_source = manifest`
- `fallback_engaged = false`
- `package_version = wv-shadow-field-baseline-2026.07.14`

Observed shadow inference result:

- `predicted_weight_kg = 18.1972`
- `confidence = 0.8111`
- `prediction_mode = shadow`
- `stub_mode = false`

This proves the Edge runtime can consume the real Cloud-exported package format after activation.

---

## Defects fixed during verification

### Defect 1: Cloud ML route dependencies bound incorrectly during test/runtime setup

Observed failure:

- `request.app.state.settings` was missing when the test application lifespan was not entered correctly

Resolution:

- use request-scoped app state access in dependency helpers
- run verification through `TestClient(...)` context so FastAPI lifespan initializes cleanly

### Defect 2: `cloud-weighvision-readmodel` Windows build script failure

Observed failure:

- `cp` was not recognized during `npm run build`

Resolution:

- `cloud-layer/cloud-weighvision-readmodel/package.json`
- replaced `cp openapi.yaml dist/` with a Node-based copy command

### Defect 3: exported package manifest entrypoint path was incompatible with Edge activation

Observed failure:

- real package activation fell back to stub mode because manifest `entrypoint` was emitted as a version-prefixed path, causing a doubled directory segment after extraction

Resolution:

- `cloud-layer/cloud-ml-model-service/app/routes.py`
- changed published manifest `entrypoint` to `model/model.json`
- added assertion coverage in `cloud-layer/cloud-ml-model-service/tests/test_api.py`

### Defect 4: Cloud ML container path defaults were brittle in Docker

Observed failure:

- `cloud-ml-model-service` crashed in container because dataset and artifact path defaults depended on a host-only parent-directory assumption

Resolution:

- `cloud-layer/cloud-ml-model-service/app/config.py`
- added runtime-safe default resolvers for artifact root and dataset path

### Defect 5: Cloud ML service healthcheck command did not match the image contents

Observed failure:

- Docker healthcheck used `wget` while the image only guaranteed `curl`

Resolution:

- `cloud-layer/docker-compose.yml`
- changed healthcheck to `curl -fsS http://localhost:8000/api/health`

### Defect 6: Cloud registry rows returned JSON fields as strings in runtime paths

Observed failure:

- `manifest`, `metrics`, `features`, `hyperparameters`, and `metadata` could surface as JSON strings, breaking package resolve and download flows

Resolution:

- `cloud-layer/cloud-ml-model-service/app/routes.py`
- normalized JSON-valued row fields before building API payloads
- added serializer regression coverage in `cloud-layer/cloud-ml-model-service/tests/test_api.py`

### Defect 7: BFF to ML internal base URL was inconsistent for container routing

Observed failure:

- `cloud-api-gateway-bff` could route to the wrong ML service host or port inside Docker

Resolution:

- `cloud-layer/cloud-api-gateway-bff/src/services/dashboardService.ts`
- aligned ML base URL resolution to `ML_MODEL_SERVICE_BASE_URL` first, with Docker-safe default `http://cloud-ml-model-service:8000`

### Defect 8: Edge policy-sync did not send the query/header shape expected by Cloud BFF

Observed failure:

- policy sync returned `400 MISSING_TENANT_ID` because tenant/farm/barn query names and tenant header were not aligned with the BFF contract

Resolution:

- `edge-layer/edge-policy-sync/src/services/policySyncService.ts`
- switched to `tenant_id`, `farm_id`, `barn_id` query parameters and added `x-tenant-id`

### Defect 9: Edge inference outbox table was missing in local smoke runtime

Observed failure:

- inference job completion failed with `relation "sync_outbox" does not exist`

Resolution:

- `edge-layer/edge-vision-inference/app/db.py`
- added `sync_outbox` schema bootstrap and indexes inside `ensure_schema()`

### Defect 10: Edge inference result readback returned `metadata` as a JSON string

Observed failure:

- smoke summary could not read `prediction_mode`, `package_id`, `package_version`, and related runtime fields because result-read API returned `metadata` as a string

Resolution:

- `edge-layer/edge-vision-inference/app/db.py`
- normalized `metadata` on `get_inference_result()` and `get_inference_results_by_session()`
- added regression tests in `edge-layer/edge-vision-inference/tests/test_db.py`

---

## Batch 4 closure statement

Batch 4 exit gate is satisfied at repository, unit-test, and local Docker Compose smoke level:

- Cloud has dataset contract, baseline model training route, registry, and subscription API
- Cloud exports a deployable package artifact with checksum and download path
- Edge can identify, pull, activate, and execute the package in shadow mode
- Edge job-service can sync prediction metadata back through the outbox payload
- full mock-data container smoke proves `train -> publish -> subscribe -> activate -> infer -> readback`

Recommended next step after Batch 4:

- improve feature engineering and model families for `WO-IOT-FD-015` promotion quality, because the current linear baseline underperforms the naive comparator on validation data
