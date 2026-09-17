# Edge Layer Setup and Run Guide

**Purpose:** Canonical runbook for local edge deployment and verification.  
**Scope:** Compose layout, scripts, startup flow, verification, and troubleshooting.  
**Owner:** FarmIQ Edge Team  
**Last updated:** 2026-07-16

---

## Canonical deployment layout

Use these files with clear roles:

| Path | Role |
|---|---|
| `edge-layer/docker-compose.yml` | Common service definitions shared by all edge deployments |
| `edge-layer/docker-compose.dev.yml` | Local infra, host ports, and development overrides |
| `edge-layer/docker-compose.batch4-smoke.yml` | Batch 4 control-plane smoke override only |
| `edge-layer/docker-compose.batch5-e2e.yml` | Batch 5 E2E override only |
| `edge-layer/scripts/deploy.ps1` / `deploy.sh` | Canonical operator entrypoint |
| `edge-layer/scripts/run-seeds.ps1` / `run-seeds.sh` | DB migration + seed flow |
| `edge-layer/scripts/edge-smoke-http.ps1` / `edge-smoke-http.sh` | HTTP smoke flow |
| `edge-layer/scripts/edge-smoke-mqtt.ps1` / `edge-smoke-mqtt.sh` | MQTT smoke flow |

Rules:

- For normal local deploy, always use `docker-compose.yml` together with `docker-compose.dev.yml`.
- Do not use the batch override files for regular startup; they are scenario-specific overlays for IoT verification work.
- Prefer `scripts/deploy.ps1` or `scripts/deploy.sh` instead of typing compose commands ad hoc.

---

## Standard local workflow

### 1. Prepare environment

From `edge-layer/`:

```bash
cp .env.example .env
```

Minimum important variables:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
- `CLOUD_INGESTION_URL` when using real cloud-layer integration
- `BFF_BASE_URL` when using real policy-sync against cloud BFF

### 2. Start the stack

PowerShell:

```powershell
.\scripts\deploy.ps1 up
```

Bash:

```bash
./scripts/deploy.sh up
```

If you need the optional `edge-feed-intake` service:

PowerShell:

```powershell
.\scripts\deploy.ps1 up -WithFeedIntake
```

Bash:

```bash
./scripts/deploy.sh up --with-feed-intake
```

### 3. Check status

```powershell
.\scripts\deploy.ps1 ps
```

or

```bash
./scripts/deploy.sh ps
```

### 4. Seed databases

```powershell
.\scripts\deploy.ps1 seed
```

or

```bash
./scripts/deploy.sh seed
```

### 5. Run smoke verification

HTTP flow:

```powershell
.\scripts\deploy.ps1 smoke-http
```

MQTT flow:

```powershell
.\scripts\deploy.ps1 smoke-mqtt
```

### 6. Stop the stack

```powershell
.\scripts\deploy.ps1 down
```

Reset all local data:

```powershell
.\scripts\deploy.ps1 down -Volumes
```

---

## Direct compose commands

Use direct compose only when debugging:

```bash
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml up -d --build
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml ps
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml down
```

Optional feed-intake profile:

```bash
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml --profile feed-intake up -d --build
```

---

## Local ports

| Service | Host Port | Notes |
|---|---:|---|
| edge-mqtt-broker | 5100 | MQTT |
| edge-cloud-ingestion-mock | 5102 | Dev-only mock |
| edge-ingress-gateway | 5103 | `/api/health`, `/api-docs` |
| edge-telemetry-timeseries | 5104 | `/api/health`, `/api-docs` |
| edge-weighvision-session | 5105 | `/api/health`, `/api-docs` |
| edge-media-store | 5106 | `/api/health`, `/api-docs` |
| edge-vision-inference | 5107 | `/api/health`, `/api-docs` |
| edge-sync-forwarder | 5108 | `/api/health`, `/api-docs` |
| edge-policy-sync | 5109 | `/api/health`, `/api-docs` |
| edge-observability-agent | 5111 | `/api/v1/ops/edge/status` |
| edge-feed-intake | 5112 | Optional profile |
| edge-ops-web | 5113 | Canonical browser entrypoint |
| edge-retention-janitor | 5114 | `/api/health`, `/api-docs` |
| postgres | 5141 | Local edge DB |
| pgadmin | 5438 | Optional local DB UI |
| minio | 9000 / 9001 | API / Console |

---

## Compose model

### `docker-compose.yml`

Treat this as the shared edge service catalog:

- service definitions
- common env defaults
- common dependencies
- common health checks

It is not the preferred standalone file for local operation.

### `docker-compose.dev.yml`

This is the local operator overlay:

- adds `postgres`, `pgadmin`, `minio`, and `edge-local-ntp`
- binds host ports
- swaps to `Dockerfile.dev`
- mounts source for development
- makes `edge-feed-intake` optional via profile

### Batch override files

Use only with IoT-layer runbooks:

- `docker-compose.batch4-smoke.yml`
- `docker-compose.batch5-e2e.yml`

They are not part of the default deploy path.

---

## Quick verification checklist

```bash
curl -I http://localhost:5113/
curl http://localhost:5113/api/health
curl http://localhost:5111/api/v1/ops/edge/status
curl http://localhost:5107/api/health
curl http://localhost:5108/api/v1/sync/state
```

Expected:

- Ops Web returns `200`
- Ops health returns `{"status":"ok"}`
- Observability returns aggregated edge status JSON
- Vision inference returns healthy
- Sync forwarder returns state JSON

---

## Troubleshooting

### Services fail to start

Check:

```bash
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml logs --tail=200 <service>
```

Common causes:

- host port already in use
- local `.env` missing required overrides
- database not ready yet

### Postgres-related failures

Check:

```bash
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml exec -T postgres pg_isready -U farmiq -d farmiq
```

If schema or seed is missing, rerun:

```powershell
.\edge-layer\scripts\deploy.ps1 seed
```

### Ops Web is up but marked unhealthy

The container health check now uses `http://localhost/api/health`. If it still fails, inspect:

```bash
docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml logs --tail=100 edge-ops-web
```

### Sync forwarder cannot reach cloud

Verify the configured URL in `.env`:

- `CLOUD_INGESTION_URL`
- `CLOUD_AUTH_MODE`
- `CLOUD_API_KEY`
- `CLOUD_HMAC_SECRET`

For local-only mode, the default mock target is `edge-cloud-ingestion-mock`.

---

## Related docs

- [00-overview.md](00-overview.md)
- [01-edge-services.md](01-edge-services.md)
- [03-edge-ops-web.md](03-edge-ops-web.md)
- [04-local-compose-setup.md](04-local-compose-setup.md)
- [05-evidence-local-compose.md](05-evidence-local-compose.md)
- [../../edge-layer/README.md](../../edge-layer/README.md)
