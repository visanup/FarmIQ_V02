# FarmIQ Apps

This directory contains the frontend applications that sit on top of the cloud layer:

- `dashboard-web`
- `admin-web`

## Canonical deployment patterns

### 1. Integrated Docker deploy

Use this when you want the UIs to run together with the cloud stack.

PowerShell:

```powershell
cd apps
.\scripts\deploy.ps1 -Mode up
.\scripts\deploy.ps1 -Mode verify
```

Bash:

```bash
cd apps
./scripts/deploy.sh up
./scripts/deploy.sh verify
```

Notes:

- The apps are started through `cloud-layer/docker-compose.yml` plus `cloud-layer/docker-compose.dev.yml`.
- There is no standalone `apps/docker-compose.yml` anymore.
- `dashboard-web` is exposed on `http://localhost:5142`.
- `admin-web` is exposed on `http://localhost:5143`.

### 2. App-local development

Use this when you only need one frontend and want Vite hot reload.

`dashboard-web`:

```powershell
cd apps\dashboard-web
.\scripts\bootstrap.ps1
npm run dev
```

`admin-web`:

```powershell
cd apps\admin-web
npm install
npm run dev
```

## Rules for future changes

- Keep Docker deploy entrypoints under `apps/scripts/deploy.*`.
- Keep app-local bootstrap logic inside the specific app directory.
- If a new frontend is added, wire it into `cloud-layer/docker-compose.yml` and update `apps/scripts/deploy.*` in the same change.
