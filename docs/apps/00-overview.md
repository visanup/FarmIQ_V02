Purpose: Define how FarmIQ frontend apps are organized and deployed.
Scope: `dashboard-web`, `admin-web`, Docker profile `ui`, and app-local development.
Owner: FarmIQ Frontend Team
Last updated: 2026-07-16

---

## Apps overview

FarmIQ frontends live under `apps/` and are deployed in one of two modes:

1. Integrated Docker mode, where the apps run as part of the cloud stack.
2. App-local mode, where a single app is started with Vite for fast development.

Current apps:

- `dashboard-web`
- `admin-web`

The canonical Docker wiring for both apps lives in:

- `cloud-layer/docker-compose.yml`
- `cloud-layer/docker-compose.dev.yml`

The canonical app deploy entrypoints live in:

- `apps/scripts/deploy.ps1`
- `apps/scripts/deploy.sh`

Detailed runbook:

- `docs/apps/01-deployment-runbook.md`
