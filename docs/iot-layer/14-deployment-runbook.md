Purpose: Canonical local deployment runbook for the IoT WeighVision stack.  
Scope: Standardize Docker Compose, scripts, and environment setup so the next deploy uses one repeatable path.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-16  

---

## Canonical files

Use these files as the single source of truth for local IoT deploy:

- `iot-layer/docker-compose.yml`
  - main operator stack
- `iot-layer/docker-compose.capture-smoke.yml`
  - overlay for hardware-free capture smoke proof
- `iot-layer/scripts/deploy.ps1`
  - standard Windows entrypoint
- `iot-layer/scripts/deploy.sh`
  - standard Bash entrypoint
- `iot-layer/README.md`
  - quick navigation and command summary

Important:

- this runbook is for the **local** deploy path
- for field or production-intent usage, use `docs/iot-layer/15-production-template-runbook.md`

Do not use ad hoc one-off commands as the default workflow when these scripts cover the same task.

---

## Deployment patterns

### 1. Core stack

Use this when you need the UI, calibrator, and metadata-forwarding service without live capture hardware.

Services:

- `ui-app`
- `weight-vision-calibrator`
- `weight-vision-service`

Windows:

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action core
```

Bash:

```bash
cd iot-layer
./scripts/deploy.sh core
```

Direct compose equivalent:

```bash
docker compose up -d --build ui-app weight-vision-calibrator weight-vision-service
```

### 2. Full local capture stack

Use this when you need live RTSP cameras and the serial scale.

Services:

- all `core` services
- `weight-vision-capture` through profile `capture`

Windows:

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action full
```

Bash:

```bash
cd iot-layer
./scripts/deploy.sh full
```

Direct compose equivalent:

```bash
docker compose --profile capture up -d --build ui-app weight-vision-calibrator weight-vision-service weight-vision-capture
```

### 3. Hardware-free container smoke

Use this for `weight-vision-capture` image startup and model runtime proof without RTSP or scale hardware.

Windows:

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action smoke
```

Bash:

```bash
cd iot-layer
./scripts/deploy.sh smoke
```

Direct compose equivalent:

```bash
docker compose -f docker-compose.yml -f docker-compose.capture-smoke.yml up -d --build weight-vision-capture-smoke
```

Expected evidence output:

- `docs/iot-layer/evidence/batch3-yolo26-container-smoke.json`

---

## Pre-deploy checklist

### Core

- copy `iot-layer/weight-vision-service/.env.example` to `iot-layer/weight-vision-service/.env`
- confirm edge endpoints, MQTT settings, and tenant identifiers are correct

### Full capture

- complete all `core` checks
- copy `iot-layer/env.example` to `iot-layer/.env`
- set RTSP and scale values in `iot-layer/.env` or your shell environment
- verify `MAPS_PATH` points to `camera-config/calibration-camera/stereo_rectify_maps.yml`
- verify Docker host access to the serial device and camera network

### Smoke

- ensure Docker is running
- ensure the promoted runtime model exists at `iot-layer/camera-config/model/best.pt`

---

## Standard operational commands

### Status

Windows:

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action status
```

Bash:

```bash
cd iot-layer
./scripts/deploy.sh status
```

### Logs

All services:

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action logs
```

Single service:

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action logs -Service weight-vision-service
```

### Capture refresh after code-only changes

Use this after changing Python source in `weight-vision-capture/` when the image itself did not change.

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action capture-recreate
```

### Capture rebuild after Docker or dependency changes

Use this after changing `Dockerfile`, dependency files, or anything that must be baked into the image.

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action capture-rebuild
```

### Render resolved compose config

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action config
```

### Stop everything cleanly

```powershell
cd .\iot-layer
.\scripts\deploy.ps1 -Action down
```

---

## Compose rules to keep future deploys stable

- `docker-compose.yml` is the only base file for the IoT local stack
- `docker-compose.capture-smoke.yml` is only an overlay; do not merge smoke-only services into the hardware path
- use the `capture` profile only for the live `weight-vision-capture` service
- use `capture-recreate` for code-only changes and `capture-rebuild` for image changes
- write smoke evidence to `docs/iot-layer/evidence/` so audit artifacts stay outside the runtime code directories
- keep environment defaults in example files; do not hardcode machine-specific RTSP or serial values in compose

---

## Related runbooks

- `docs/iot-layer/11-weight-vision-capture-container-smoke-runbook.md`
- `docs/iot-layer/09-final-weight-local-smoke-runbook.md`
- `docs/iot-layer/13-cloud-edge-ai-control-plane-runbook.md`
- `docs/iot-layer/15-production-template-runbook.md`
- `docs/iot-layer/16-mock-capture-injection-runbook.md`
