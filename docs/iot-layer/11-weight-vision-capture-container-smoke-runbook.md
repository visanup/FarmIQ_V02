Purpose: Standard rebuild and verification runbook for `weight-vision-capture` container smoke with promoted YOLO26.  
Scope: Local/container proof only. This path does not require live RTSP cameras or serial scale hardware.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-14  

---

## Preconditions

- current workspace root: `D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02`
- promoted model already copied to `iot-layer/camera-config/model/best.pt`
- backup model kept at `iot-layer/camera-config/model/best.yolo12-backup-20260714.pt`
- Docker Desktop Linux engine is running
- note: active runtime reads `camera-config/model/best.pt`; the training workspace is only a reference and benchmark source in this smoke flow

---

## Rebuild and start

Run from `iot-layer/`:

```powershell
docker compose `
  -f .\docker-compose.yml `
  -f .\docker-compose.capture-smoke.yml `
  up -d --build weight-vision-capture-smoke
```

---

## Health verification

```powershell
docker compose `
  -f .\docker-compose.yml `
  -f .\docker-compose.capture-smoke.yml `
  ps weight-vision-capture-smoke
```

Expected status:

- service name: `weight-vision-capture-smoke`
- container status: `Up (...) (healthy)`

---

## Evidence verification

Verify the generated host-side evidence file:

```powershell
Get-Content `
  'D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\docs\iot-layer\evidence\batch3-yolo26-container-smoke.json'
```

Expected proof:

- `baseline_yolo12` loads from `camera-config/model/best.yolo12-backup-20260714.pt`
- `yolo26_promoted_bestpt` loads from `camera-config/model/best.pt`
- `yolo26_candidate_local` and `yolo26_promoted_bestpt` return matching smoke detections on the same sample image
- every verified profile reports `task: "segment"`

---

## Cleanup

```powershell
docker compose `
  -f .\docker-compose.yml `
  -f .\docker-compose.capture-smoke.yml `
  stop weight-vision-capture-smoke
```

If full removal is required:

```powershell
docker compose `
  -f .\docker-compose.yml `
  -f .\docker-compose.capture-smoke.yml `
  rm -f weight-vision-capture-smoke
```

---

## Notes

- this smoke path validates container startup, runtime profile resolution, and sample-image inference only
- this smoke path does not validate live camera capture, scale stabilization, RTSP reconnect behavior, or hardware IO
- live-bench replay is still required before field rollout
