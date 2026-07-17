Purpose: Define the canonical local deployment workflow for the FarmIQ cloud layer.
Scope: Compose file roles, startup modes, verification, UI profile, and troubleshooting entrypoints.
Owner: FarmIQ Platform Team
Last updated: 2026-07-16

---

## Canonical file roles

- `cloud-layer/docker-compose.yml`
  - shared baseline services
  - production-oriented defaults
  - source of truth for service membership and ports

- `cloud-layer/docker-compose.dev.yml`
  - local development overrides
  - mount-based development behavior
  - local-only resource limits and debug settings

- `cloud-layer/docker-compose.prisma.yml`
  - Prisma Studio only

- `cloud-layer/docker-compose.batch4-smoke.yml`
- `cloud-layer/docker-compose.batch5-e2e.yml`
- `cloud-layer/docker-compose-phase09.yml`
  - scenario-specific overlays
  - do not use as the default daily startup path

---

## Canonical entrypoints

Use these first:

- `cloud-layer/scripts/deploy.ps1`
- `cloud-layer/scripts/deploy.sh`

Legacy numbered scripts remain as implementation building blocks, but deploy operators should start from `deploy.*`.

---

## Standard startup paths

### 1. Normal local startup

PowerShell:

```powershell
cd cloud-layer
.\scripts\deploy.ps1 -Mode full -RunSeeds
```

Bash:

```bash
cd cloud-layer
./scripts/deploy.sh full --run-seeds
```

Use this when Docker Desktop can build the full stack reliably.

### 2. Batched local startup

PowerShell:

```powershell
cd cloud-layer
.\scripts\deploy.ps1 -Mode batched -RunSeeds
```

To resume from a later batch:

```powershell
.\scripts\deploy.ps1 -Mode batched -FromBatch pipeline -ToBatch gateway
```

Use this when full startup is unstable or too heavy on local CPU and RAM.

### 3. Verification

PowerShell:

```powershell
.\scripts\deploy.ps1 -Mode verify
```

This runs:

- compose env verification
- BFF tenant route verification
- dashboard-facing API verification

### 4. Stop the cloud stack

```powershell
.\scripts\deploy.ps1 -Mode down
```

---

## UI startup

Frontend containers are part of the cloud compose stack but protected behind profile `ui`.

Use:

```powershell
cd apps
.\scripts\deploy.ps1 -Mode up
```

or directly:

```powershell
docker compose -f ..\cloud-layer\docker-compose.yml -f ..\cloud-layer\docker-compose.dev.yml --profile ui up -d --build dashboard-web admin-web
```

---

## What not to do

- Do not start daily development from smoke overlay files unless you are executing that exact scenario.
- Do not create another compose file for `apps/`.
- Do not bypass `docker-compose.dev.yml` for local app or service development unless you explicitly want production-like behavior.

---

## Troubleshooting entrypoints

- RabbitMQ queue mismatch:
  - `cloud-layer/scripts/09-fix-rabbitmq-queue.ps1`

- Prisma Studio issues:
  - `cloud-layer/scripts/10-diagnose-prisma-studio.ps1`

- Compose env verification only:
  - `cloud-layer/scripts/06-verify-compose.ps1`

- Seed only:
  - `cloud-layer/scripts/04-run-seeds.ps1`
