Purpose: Quick local compose reference for edge operators.  
Scope: Short commands, canonical entrypoint, and current ports.  
Owner: FarmIQ Edge Team  
Last updated: 2026-07-16

---

## Canonical entrypoint

Preferred browser entrypoint:

- `http://localhost:5113`

Preferred operator commands:

```powershell
cd edge-layer
.\scripts\deploy.ps1 up
.\scripts\deploy.ps1 ps
.\scripts\deploy.ps1 seed
.\scripts\deploy.ps1 smoke-http
.\scripts\deploy.ps1 down
```

---

## Equivalent compose commands

```bash
cd edge-layer
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

---

## Current local ports

| Service | Host Port |
|---|---:|
| edge-mqtt-broker | 5100 |
| edge-cloud-ingestion-mock | 5102 |
| edge-ingress-gateway | 5103 |
| edge-telemetry-timeseries | 5104 |
| edge-weighvision-session | 5105 |
| edge-media-store | 5106 |
| edge-vision-inference | 5107 |
| edge-sync-forwarder | 5108 |
| edge-policy-sync | 5109 |
| edge-observability-agent | 5111 |
| edge-feed-intake | 5112 |
| edge-ops-web | 5113 |
| edge-retention-janitor | 5114 |
| postgres | 5141 |
| pgadmin | 5438 |
| minio | 9000 / 9001 |

---

## Notes

- `docker-compose.yml` is the shared base; pair it with `docker-compose.dev.yml` for local operation.
- `docker-compose.batch4-smoke.yml` and `docker-compose.batch5-e2e.yml` are scenario-specific overlays, not default deploy files.
- `edge-feed-intake` is optional and should be started with the `feed-intake` profile only when needed.
