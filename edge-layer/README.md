# Edge Layer Deploy Guide

This directory has one canonical local deploy path and two scenario-specific override files.

## Structure

| Path | Role |
|---|---|
| `docker-compose.yml` | Common edge service definitions. Not intended to be the only file for local runs. |
| `docker-compose.dev.yml` | Local infrastructure, host ports, and development overrides. |
| `docker-compose.batch4-smoke.yml` | Batch 4 control-plane smoke override. Use only with the IoT runbook. |
| `docker-compose.batch5-e2e.yml` | Batch 5 E2E override. Use only with the IoT runbook. |
| `scripts/deploy.ps1` / `scripts/deploy.sh` | Canonical operator entrypoint for local edge lifecycle. |
| `scripts/run-seeds.*` | Seed and migrate local edge databases. |
| `scripts/edge-smoke-http.*` / `scripts/edge-smoke-mqtt.*` | Focused smoke verification flows. |
| `../docs/edge-layer/02-setup-run.md` | Detailed runbook. |

## Standard local flow

1. Copy `.env.example` to `.env`.
2. Start the stack:
   - PowerShell: `.\scripts\deploy.ps1 up`
   - Bash: `./scripts/deploy.sh up`
3. Optional feed-intake profile:
   - PowerShell: `.\scripts\deploy.ps1 up -WithFeedIntake`
   - Bash: `./scripts/deploy.sh up --with-feed-intake`
4. Seed databases:
   - PowerShell: `.\scripts\deploy.ps1 seed`
   - Bash: `./scripts/deploy.sh seed`
5. Verify:
   - PowerShell: `.\scripts\deploy.ps1 smoke-http`
   - Bash: `./scripts/deploy.sh smoke-http`

Edge Ops Web is served at `http://localhost:5113`.

## Direct compose reference

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

For the full runbook and troubleshooting notes, use [docs/edge-layer/02-setup-run.md](../docs/edge-layer/02-setup-run.md).
