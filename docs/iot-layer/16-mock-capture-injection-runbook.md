Purpose: Provide a simple operator path for injecting mock capture metadata and images into the IoT-to-Edge flow.  
Scope: One-shot test data injection through `weight-vision-service` without running the live capture container.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-16  

---

## What this script does

Use `iot-layer/scripts/inject-mock-capture.ps1` when you want to:

- reuse an existing capture metadata JSON file
- copy the corresponding source images into a temporary capture folder
- rewrite `image_id` and `session_id` to a fresh test session
- optionally override the weight
- run `weight-vision-service` once with `METADATA_FILE_ONCE`

This is useful for:

- local regression checks
- edge integration checks
- reprocessing a known image set without live hardware

---

## Input expectation

The script expects a metadata file under a standard capture layout such as:

- `iot-layer/weight-vision-capture/data/metadata/<capture>.json`

It then looks for matching images under the sibling `images/` directory using the original `image_id`:

- `iot-layer/weight-vision-capture/data/images/<image_id>_*`

---

## Standard command

```powershell
cd .\
powershell -ExecutionPolicy Bypass -File iot-layer\scripts\inject-mock-capture.ps1 `
  -SourceMetadataPath iot-layer\weight-vision-capture\data\metadata\20260210_073143.json `
  -TenantId tenant-local-test `
  -FarmId farm-local-test `
  -BarnId barn-local-test `
  -DeviceId wv-local-test `
  -StationId station-local-test
```

---

## Override weight

```powershell
cd .\
powershell -ExecutionPolicy Bypass -File iot-layer\scripts\inject-mock-capture.ps1 `
  -SourceMetadataPath iot-layer\weight-vision-capture\data\metadata\20260210_073143.json `
  -TenantId tenant-local-test `
  -FarmId farm-local-test `
  -BarnId barn-local-test `
  -DeviceId wv-local-test `
  -StationId station-local-test `
  -UseOverrideWeight `
  -OverrideWeightKg 3.33
```

---

## Dry-run mode

Use this when you want to validate metadata and event construction without sending uploads or edge API writes:

```powershell
cd .\
powershell -ExecutionPolicy Bypass -File iot-layer\scripts\inject-mock-capture.ps1 `
  -SourceMetadataPath iot-layer\weight-vision-capture\data\metadata\20260210_073143.json `
  -DryRun
```

---

## Default targets

Unless you override them, the script points to:

- media store: `http://localhost:5106`
- session service: `http://localhost:5105`
- edge inference: `http://localhost:5107`
- MQTT hosts: `127.0.0.1:5100`

---

## Output

The script returns a JSON summary with:

- generated `session_id`
- generated metadata path
- temporary capture root
- copied image paths
- dry-run status
- log file path

The execution log is written under:

- `docs/iot-layer/evidence/`

---

## Related flows

- local deploy: `docs/iot-layer/14-deployment-runbook.md`
- production-template deploy: `docs/iot-layer/15-production-template-runbook.md`
- full Cloud-Edge rerun: `docs/iot-layer/13-cloud-edge-ai-control-plane-runbook.md`
- production-like local rerun with `.env` real business identifiers: `docs/iot-layer/17-prodlike-t001-e2e-runbook.md`
