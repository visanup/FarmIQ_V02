# IoT Layer Operations

This directory contains the local device-side services and operator tooling for the FarmIQ WeighVision flow.

## Canonical deployment assets

- `docker-compose.yml`
  - Main local operator stack.
  - Runs `ui-app`, `weight-vision-calibrator`, and `weight-vision-service`.
  - Adds `weight-vision-capture` only when the `capture` profile is enabled.
- `docker-compose.capture-smoke.yml`
  - Hardware-free overlay for `weight-vision-capture-smoke`.
  - Use this only for container startup and model-runtime smoke proof.
- `scripts/deploy.ps1`
  - Windows-first entrypoint for local deploy, restart, smoke, and teardown.
- `scripts/deploy.sh`
  - Bash entrypoint with the same actions as the PowerShell script.
- `scripts/deploy-prod-template.ps1`
  - Production-intent template that makes live capture profile usage explicit.
- `scripts/deploy-prod-template.sh`
  - Bash version of the production-intent template.
- `scripts/inject-mock-capture.ps1`
  - One-shot helper for replaying metadata and source images through `weight-vision-service`.
- `../docs/iot-layer/14-deployment-runbook.md`
  - Canonical runbook for the deployment flow.
- `../docs/iot-layer/15-production-template-runbook.md`
  - Production-template runbook for field or production-intent deploy usage.
- `../docs/iot-layer/16-mock-capture-injection-runbook.md`
  - Mock capture replay runbook.
- `../docs/iot-layer/17-prodlike-t001-e2e-runbook.md`
  - Production-like local E2E runbook using the real non-IP parameters from `weight-vision-service/.env`.

## Quick start

Windows:

```powershell
.\scripts\deploy.ps1 -Action core
.\scripts\deploy.ps1 -Action full
.\scripts\deploy.ps1 -Action smoke
.\scripts\deploy.ps1 -Action status
```

Linux:

```bash
./scripts/deploy.sh core
./scripts/deploy.sh full
./scripts/deploy.sh smoke
./scripts/deploy.sh status
```

## Environment files

- `env.example`
  - Capture runtime defaults for RTSP, scale, and inference tuning.
- `weight-vision-service/.env.example`
  - Service-to-edge connectivity and buffering settings.

Copy only the files you need for the chosen flow:

- `core`: `weight-vision-service/.env`
- `full`: `weight-vision-service/.env` and `./.env`
- `smoke`: no live camera or scale config required

## Supported flows

- `core`
  - UI and processing services without live capture hardware.
- `full`
  - Core stack plus `weight-vision-capture` using the `capture` profile.
- `capture-recreate`
  - Recreate the capture container after code-only changes.
- `capture-rebuild`
  - Rebuild and recreate the capture container after image or dependency changes.
- `smoke`
  - Build and run `weight-vision-capture-smoke` with the compose overlay.

For detailed commands, expected outputs, and troubleshooting, use `../docs/iot-layer/14-deployment-runbook.md`.

## Production note

With the current compose file, live `weight-vision-capture` is behind the `capture` profile.

- local smoke flow: use `scripts/deploy.ps1`
- production-intent flow: use `scripts/deploy-prod-template.ps1`
- mock metadata and image replay: use `scripts/inject-mock-capture.ps1`
