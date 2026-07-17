Purpose: Provide the canonical deploy procedure for FarmIQ frontend apps.
Scope: Docker deploy, verification, stop flow, and local app development.
Owner: FarmIQ Frontend Team
Last updated: 2026-07-16

---

## Canonical rules

- Do not add a standalone compose file under `apps/`.
- Start frontend containers through the cloud-layer compose files only.
- Use `apps/scripts/deploy.*` as the first entrypoint for frontend deploy tasks.

---

## Docker deploy

### Start both apps

PowerShell:

```powershell
cd apps
.\scripts\deploy.ps1 -Mode up
```

Bash:

```bash
cd apps
./scripts/deploy.sh up
```

### Start only one app

```powershell
.\scripts\deploy.ps1 -Mode up -Target dashboard-web
.\scripts\deploy.ps1 -Mode up -Target admin-web
```

```bash
./scripts/deploy.sh up dashboard-web
./scripts/deploy.sh up admin-web
```

### Verify

```powershell
.\scripts\deploy.ps1 -Mode verify
```

```bash
./scripts/deploy.sh verify
```

Expected URLs:

- `dashboard-web`: `http://localhost:5142`
- `admin-web`: `http://localhost:5143`

### Stop only the apps

```powershell
.\scripts\deploy.ps1 -Mode down
```

```bash
./scripts/deploy.sh down
```

This stops only the UI containers. It does not tear down the full cloud stack.

---

## App-local development

### dashboard-web

```powershell
cd apps\dashboard-web
.\scripts\bootstrap.ps1
npm run dev
```

### admin-web

```powershell
cd apps\admin-web
npm install
npm run dev
```

Use app-local mode when you need fast frontend iteration and do not need to rebuild container images.
