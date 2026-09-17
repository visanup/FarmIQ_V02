Purpose: Provide a production-like deployment template for the IoT WeighVision stack.  
Scope: Separate field or production-intent operator commands from the local smoke-oriented deploy script.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-16  

---

## Important boundary

This is a **production-template runbook**, not proof that the current repository deploy script has already been used in live production unchanged.

What this template does:

- gives operators a production-intent command set
- removes smoke-only actions from the main path
- makes `weight-vision-capture` activation explicit

What it does not claim:

- that the exact script was already executed on a live production site
- that this repository currently contains a separate production compose file

---

## Canonical template script

- PowerShell: `iot-layer/scripts/deploy-prod-template.ps1`
- Bash: `iot-layer/scripts/deploy-prod-template.sh`

These scripts use only `iot-layer/docker-compose.yml`.

They do **not** use `docker-compose.capture-smoke.yml`.

---

## Does live capture require a compose profile?

Yes. With the current compose file, `weight-vision-capture` is defined under:

```yaml
profiles:
  - capture
```

That means:

- plain `docker compose up -d` will not include `weight-vision-capture`
- for live RTSP and scale capture, the operator should run with `--profile capture`
- the production-template scripts always enable the capture profile for `capture`, `full`, `status`, `logs`, `config`, and `down`

---

## Template actions

- `core`
  - starts `ui-app`, `weight-vision-calibrator`, `weight-vision-service`
- `capture`
  - starts only `weight-vision-capture` with `--profile capture`
- `full`
  - starts the full stack including live capture with `--profile capture`
- `status`
  - shows the stack with capture profile context enabled
- `logs`
  - tails logs for all services or a selected service
- `config`
  - renders resolved compose config with capture profile included
- `down`
  - stops the stack and removes orphans

---

## PowerShell examples

```powershell
cd .\iot-layer
.\scripts\deploy-prod-template.ps1 -Action core
.\scripts\deploy-prod-template.ps1 -Action capture
.\scripts\deploy-prod-template.ps1 -Action full
.\scripts\deploy-prod-template.ps1 -Action status
.\scripts\deploy-prod-template.ps1 -Action logs -Service weight-vision-capture
.\scripts\deploy-prod-template.ps1 -Action down
```

If you need image rebuilds in the same template flow:

```powershell
cd .\iot-layer
.\scripts\deploy-prod-template.ps1 -Action full -BuildImages
```

---

## Bash examples

```bash
cd iot-layer
./scripts/deploy-prod-template.sh core
./scripts/deploy-prod-template.sh capture
./scripts/deploy-prod-template.sh full
./scripts/deploy-prod-template.sh status
./scripts/deploy-prod-template.sh logs weight-vision-capture
./scripts/deploy-prod-template.sh down
```

To include `--build` in the Bash template flow:

```bash
cd iot-layer
BUILD_IMAGES=1 ./scripts/deploy-prod-template.sh full
```

---

## Operator rule

If the target is a real capture node with RTSP cameras and a scale attached, treat `capture` profile activation as mandatory in the deployment command path.
