# Batch 5 E2E Smoke Verification - 2026-07-14

Scope: `WO-IOT-FD-016`  
Owner: FarmIQ Edge and Cloud Architecture  
Verified at: 2026-07-14 (Asia/Bangkok)

---

## Objective

Prove the full Batch 5 path from Cloud control plane to Edge local shadow inference and back to Cloud readmodel without disturbing the finalized load-cell truth path.

Target exit gate:

- Edge pulls the Cloud-approved model package
- Edge runs local shadow inference
- finalized truth path remains independent
- prediction outcome syncs back to Cloud for evaluation

---

## Verification evidence

### Latest verified session

- `session_id`: `sess-batch5-e2e-6e4d33a8f8104734916b4da2cbabcd75`
- `trained_package_id`: `268fcdffac8f40bcaf02e0460306e0c5`
- `package_version`: `wv-shadow-batch5-e2e-2026.07.14`
- `shadow_inference_event_id`: `7d3ac375-fba6-4ff0-baaf-34118c50c5f5`
- `finalize_event_id`: `9e0ad63f-1d0e-46b2-afc3-7a437854192e`

### Verified Cloud session state

- `status = FINALIZED`
- `final_weight_kg = 3.33`
- one shadow inference exists with:
  - `prediction_mode = shadow`
  - `predicted_weight_kg = 0.2444`
  - `confidence = 0.8111`
  - `activation_source = manifest`
  - `feature_schema_version = 1.0`
  - `package_id = 268fcdffac8f40bcaf02e0460306e0c5`

### Verified Edge outbox state

- `weighvision.inference.completed` prediction event is present and `acked`
- outbox row ID: `7d3ac375-fba6-4ff0-baaf-34118c50c5f5`
- payload includes:
  - `predicted_weight_kg`
  - `package_id`
  - `package_version`
  - `feature_schema_version`
  - `activation_source`
  - `prediction_mode`
  - `features_used`

---

## Defects fixed during Batch 5 closeout

1. `cloud-api-gateway-bff` did not forward `Authorization` to `cloud-weighvision-readmodel` on session queries.
2. `edge-vision-inference` published `occurredAt` without `Z`, which failed `z.string().datetime()` validation in `edge-weighvision-session`.
3. `scripts/batch5-e2e-smoke.ps1` used non-UUID event IDs for services writing to `sync_outbox`.
4. `scripts/batch5-e2e-smoke.ps1` checked `session_id` at the wrong response level when proving the acked prediction event.

---

## Commands executed

### Unit verification

```powershell
python -m pytest edge-layer/edge-vision-inference/tests/test_job_service.py -o cache_dir=D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\.tmp_pytest_edge_batch5_fix
npx jest --runInBand --coverage=false tests/services/weighvisionService.spec.ts tests/controllers/weighvisionController.spec.ts
```

### Build verification

```powershell
npm run build
```

Executed in:

- `cloud-layer/cloud-api-gateway-bff`
- `edge-layer/edge-weighvision-session`

### Container verification

```powershell
docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.batch5-e2e.yml up -d --build cloud-api-gateway-bff
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f edge-layer/docker-compose.batch5-e2e.yml up -d --build edge-vision-inference
powershell -ExecutionPolicy Bypass -File scripts\batch5-e2e-smoke.ps1
```

---

## Outcome

Batch 5 is functionally closed at local Docker-backed end-to-end proof level.

Confirmed:

- Cloud control plane selected the package used by Edge
- Edge executed local shadow inference from subscribed package data
- finalized load-cell truth stayed `3.33` and was not overridden by prediction
- prediction outcome returned to Cloud readmodel with audit metadata

Non-blocking residual:

- model-subscription acknowledgement calls from `edge-vision-inference` still return `500` in the current local stack and should be followed up under the subscription-ack path hardening work; this did not block package activation, local inference, or prediction sync-back proof
