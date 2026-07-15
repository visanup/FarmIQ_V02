Purpose: Record the Batch 3 YOLO26 upgrade evidence, rollout controls, and rollback path for the IoT capture runtime.  
Scope: Runtime compatibility, reproducible benchmark evidence, and controlled activation or rollback for Edge deployment.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-14  

---

## Executive summary

Batch 3 is completed at the local runtime and benchmark level for the IoT capture stack.

Promotion update on 2026-07-14:

- `camera-config/model/best.pt` has now been overwritten with the promoted YOLO26 candidate
- the previous YOLO12-era deployed file was preserved as `camera-config/model/best.yolo12-backup-20260714.pt`

Current runtime path clarification:

- the active capture runtime does not read the candidate directly from `iot-layer/weight-vision-train-model-yolo26/...`
- the active capture runtime reads `iot-layer/camera-config/model/best.pt`
- the training workspace remains the source of benchmark and candidate-reference artifacts only

Closed work orders:

- `WO-IOT-FD-011` Validate YOLO26 runtime compatibility
- `WO-IOT-FD-012` Build YOLO12 vs YOLO26 benchmark harness
- `WO-IOT-FD-013` Add rollout config and rollback path

Additional verification completed on 2026-07-14:

- local/container smoke route added for `weight-vision-capture` without modifying the production capture profile or hardware-bound compose path
- standard runbook added in `docs/iot-layer/11-weight-vision-capture-container-smoke-runbook.md`

Exit gate result:

- YOLO26 loads and runs in the capture runtime
- YOLO12 and YOLO26 were benchmarked on the same frozen dataset subset
- rollout and rollback can be controlled through runtime config without source patching

---

## Implemented changes

### Runtime compatibility and model abstraction

Implemented files:

- `iot-layer/weight-vision-capture/yolo_infer.py`
- `iot-layer/weight-vision-capture/run_service.py`
- `iot-layer/weight-vision-capture/model_runtime.py`

Key changes:

- generalized the detector wrapper to `UltralyticsSegDetector`
- kept backward-compatible alias `YoloV12Detector` to avoid breaking old callers
- added runtime model profile resolution from `camera-config/model/runtime-config.yaml`
- added CLI support for:
  - `--model-id`
  - `--model-config`
  - `--list-model-profiles`

### Runtime profiles and rollback control

Configuration file:

- `iot-layer/camera-config/model/runtime-config.yaml`

Configured profiles:

- `baseline_yolo12`
- `baseline_yolo12_backup_20260714`
- `yolo26_promoted_bestpt`
- `yolo26_family_base`
- `yolo26_candidate_local`

Operational controls:

- `active_model` selects the normal runtime target
- `fallback_model` defines the recovery target if active-model initialization fails
- runtime now falls back automatically to the configured baseline when the active profile cannot be initialized
- `yolo26_promoted_bestpt` is the active production-style runtime profile and resolves to `camera-config/model/best.pt`
- `yolo26_candidate_local` remains a benchmark/reference profile that resolves to the training workspace artifact directly

### Benchmark harness

Implemented file:

- `iot-layer/weight-vision-capture/benchmark_yolo_models.py`

Harness behavior:

- freezes a reproducible subset from the dataset
- runs both models against the same frozen images
- computes latency and segmentation-quality metrics inside the repo
- writes JSON and Markdown evidence under `docs/iot-layer/evidence/batch3-yolo26-benchmark`

### Runtime smoke checker

Implemented file:

- `iot-layer/weight-vision-capture/check_yolo_runtime_compat.py`

Purpose:

- verify load and smoke inference for configured model profiles
- persist compatibility evidence as JSON

### Container smoke route

Implemented files:

- `iot-layer/weight-vision-capture/Dockerfile.smoke`
- `iot-layer/weight-vision-capture/requirements.smoke.txt`
- `iot-layer/docker-compose.capture-smoke.yml`

Purpose:

- provide a container startup path for `weight-vision-capture` that does not require RTSP cameras or a serial scale
- keep the existing production-oriented `weight-vision-capture` compose service unchanged
- produce container evidence under `docs/iot-layer/evidence/` for repeatable verification

### Unit coverage

Implemented test file:

- `iot-layer/weight-vision-capture/tests/test_model_runtime.py`

Covered behavior:

- config profile listing
- active profile resolution
- fallback profile resolution
- precedence of CLI value over profile value over default

---

## Evidence

### Runtime compatibility

Evidence file:

- `docs/iot-layer/evidence/batch3-yolo26-runtime-compat.json`

Observed result:

- `yolo26_promoted_bestpt`, `baseline_yolo12_backup_20260714`, `yolo26_family_base`, and `yolo26_candidate_local` all load as `segment` models
- smoke inference returns mask polygons for all verified profiles
- `yolo26_family_base` is runtime-compatible but remains a generic family/base model and is not the deployment candidate
- promoted `camera-config/model/best.pt` now resolves to the same file content as the local YOLO26 candidate

### Container smoke evidence

Evidence file:

- `docs/iot-layer/evidence/batch3-yolo26-container-smoke.json`
- `docs/iot-layer/11-weight-vision-capture-container-smoke-runbook.md`

Observed result:

- the promoted `camera-config/model/best.pt` can be loaded from the `weight-vision-capture` container smoke image
- configured model profiles can be listed from the same container path
- smoke inference can complete without live camera or scale dependencies

### Benchmark evidence

Evidence files:

- `docs/iot-layer/evidence/batch3-yolo26-benchmark/benchmark-report.json`
- `docs/iot-layer/evidence/batch3-yolo26-benchmark/benchmark-summary.md`

Frozen benchmark scope:

- dataset split: `test`
- frozen images: `16`
- baseline profile: `baseline_yolo12`
- candidate profile: `yolo26_candidate_local`

Benchmark context note:

- the benchmark compares the historical YOLO12 baseline against the direct YOLO26 candidate artifact from the training workspace
- after benchmark completion, `camera-config/model/best.pt` was promoted to the YOLO26 candidate, so active runtime path and historical benchmark baseline path are no longer the same file

Measured result:

| Metric | Baseline YOLO12 profile | YOLO26 candidate profile |
| --- | --- | --- |
| Avg latency ms | `1565.52` | `391.40` |
| Avg detections per image | `0.44` | `22.31` |
| Avg precision@0.5 | `0.4286` | `0.7853` |
| Avg recall@0.5 | `0.0100` | `0.8994` |
| Avg best IoU per GT | `0.0074` | `0.7907` |

Decision note:

- on the frozen dataset used by this benchmark, `yolo26_candidate_local` materially outperforms the current baseline in both segmentation quality and average inference latency
- the active runtime path now uses the promoted copy of that candidate through `camera-config/model/best.pt`

---

## Rollout and rollback runbook

### List profiles

```powershell
& '.\iot-layer\weight-vision-capture\.venv\Scripts\python.exe' `
  '.\iot-layer\weight-vision-capture\run_service.py' `
  --model-config '.\iot-layer\camera-config\model\runtime-config.yaml' `
  --list-model-profiles
```

### Re-run compatibility smoke

```powershell
& '.\iot-layer\weight-vision-capture\.venv\Scripts\python.exe' `
  '.\iot-layer\weight-vision-capture\check_yolo_runtime_compat.py' `
  --model-config '.\iot-layer\camera-config\model\runtime-config.yaml' `
  --output '.\docs\iot-layer\evidence\batch3-yolo26-runtime-compat.json'
```

### Re-run benchmark

```powershell
& '.\iot-layer\weight-vision-capture\.venv\Scripts\python.exe' `
  '.\iot-layer\weight-vision-capture\benchmark_yolo_models.py' `
  --model-config '.\iot-layer\camera-config\model\runtime-config.yaml' `
  --baseline-model-id baseline_yolo12 `
  --candidate-model-id yolo26_candidate_local `
  --data-yaml '.\iot-layer\weight-vision-train-model-yolo26\Chicken Segmentation.v4i.yolo26\data.yaml' `
  --max-images 16 `
  --output-dir '.\docs\iot-layer\evidence\batch3-yolo26-benchmark'
```

### Run container smoke without production hardware

```powershell
docker compose `
  -f .\docker-compose.yml `
  -f .\docker-compose.capture-smoke.yml `
  up -d --build weight-vision-capture-smoke
```

### Verify container smoke

```powershell
docker compose `
  -f .\docker-compose.yml `
  -f .\docker-compose.capture-smoke.yml `
  ps weight-vision-capture-smoke
```

```powershell
Get-Content '.\docs\iot-layer\evidence\batch3-yolo26-container-smoke.json'
```

### Promote YOLO26 candidate

Completed on 2026-07-14:

- `camera-config/model/best.pt` overwritten with the promoted YOLO26 candidate
- `active_model` changed to `yolo26_promoted_bestpt`
- `fallback_model` changed to `baseline_yolo12_backup_20260714`

Meaning:

- `weight-vision-capture` now boots the promoted YOLO26 artifact from `camera-config/model/best.pt`
- it does not need to read the training workspace artifact unless a benchmark or explicit candidate-profile test is being run

### Roll back to baseline

Update `iot-layer/camera-config/model/runtime-config.yaml`:

- set `active_model: baseline_yolo12_backup_20260714`
- keep `fallback_model: baseline_yolo12_backup_20260714`

If desired, restore the backup file content explicitly:

```powershell
Copy-Item `
  -LiteralPath '.\iot-layer\camera-config\model\best.yolo12-backup-20260714.pt' `
  -Destination '.\iot-layer\camera-config\model\best.pt' `
  -Force
```

### Automatic fallback on startup

If the configured active profile fails during detector initialization and `fallback_model` is valid, `run_service.py` now:

1. logs the active-profile initialization failure
2. switches to the configured fallback profile
3. continues startup with fallback profile thresholds and runtime settings

---

## Residual risks

| Risk | Impact | Control |
| --- | --- | --- |
| benchmark subset is local and limited to `16` frozen images | field behavior may still vary | run controlled field replay before production promotion |
| `yolo26_family_base` is load-compatible but not semantically aligned to farm classes | wrong-class predictions if activated by mistake | keep deployment target on `yolo26_candidate_local` only |
| field hardware variance may alter latency | rollout decision could differ by site | repeat smoke benchmark on target Edge hardware before field cutover |
| container smoke route does not exercise live RTSP or serial IO | hardware-specific defects may remain hidden | keep separate live-bench replay before field deployment |

---

## Recommendation

`yolo26_candidate_local` is approved for the next controlled field rollout stage, not yet for unrestricted production-wide promotion.

Recommended next step:

1. keep `yolo26_promoted_bestpt` as the active local profile for smoke and hardware replay
2. retain `baseline_yolo12_backup_20260714` as the rollback target until field replay is complete
3. if field replay regresses, restore both `active_model` and `best.pt` from the backup file
4. use the container smoke route as the default rebuild proof before any further `weight-vision-capture` image changes
