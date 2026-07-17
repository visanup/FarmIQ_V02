# Cloud Layer Scripts

Use `deploy.ps1` or `deploy.sh` as the canonical entrypoint for local cloud deployment.

## Canonical entrypoints

PowerShell:

```powershell
cd cloud-layer
.\scripts\deploy.ps1 full -RunSeeds
.\scripts\deploy.ps1 batched -RunSeeds
.\scripts\deploy.ps1 verify
.\scripts\deploy.ps1 down
```

Bash:

```bash
cd cloud-layer
./scripts/deploy.sh full --run-seeds
./scripts/deploy.sh batched --run-seeds
./scripts/deploy.sh verify
./scripts/deploy.sh down
```

## What each script family is for

- `deploy.*`
  - primary operator entrypoint
  - choose `full`, `batched`, `verify`, or `down`

- `01-*` to `05-*`
  - setup and seed building blocks
  - keep for targeted recovery tasks

- `06-*` to `08-*`
  - verification checks
  - used by `deploy.ps1 verify`

- `09-*` to `10-*`
  - troubleshooting helpers

- `Shared/Config.ps1`
  - shared compose paths, service lists, database names, and default IDs

- `Shared/Utilities.ps1`
  - shared Docker, HTTP, and migration helpers

## Recommended flows

### First-time or clean local startup

```powershell
.\scripts\deploy.ps1 full -RunSeeds
.\scripts\deploy.ps1 verify
```

### Low-resource or unstable Docker Desktop startup

```powershell
.\scripts\deploy.ps1 batched -RunSeeds
.\scripts\deploy.ps1 verify
```

### Seed only

```powershell
.\scripts\04-run-seeds.ps1
```

### Troubleshooting

```powershell
.\scripts\09-fix-rabbitmq-queue.ps1
.\scripts\10-diagnose-prisma-studio.ps1
```

## Reference docs

- `docs/cloud-layer/05-deployment-runbook.md`
- `docs/cloud-layer/RUNBOOKS.md`
