# FarmIQ Edge Ops Web

Lightweight operations UI plus `/svc/*` proxy for the local edge stack.

## Runtime modes

### Docker compose

```bash
# From edge-layer
./scripts/deploy.sh up
```

- URL: `http://localhost:5113`
- Health: `http://localhost:5113/api/health`

### Local Vite development

```bash
cd edge-ops-web
npm install
npm run dev
```

- URL: `http://localhost:5110`

## Responsibilities

- Serve the built React SPA from `dist/`
- Proxy browser traffic from `/svc/*` to internal compose services
- Expose `/api/probe/tcp` for MQTT reachability checks
- Expose `/api/health` for container health checks

## Proxy map

| Path | Target |
|---|---|
| `/svc/ingress/*` | `http://edge-ingress-gateway:3000` |
| `/svc/telemetry/*` | `http://edge-telemetry-timeseries:3000` |
| `/svc/weighvision/*` | `http://edge-weighvision-session:3000` |
| `/svc/media/*` | `http://edge-media-store:3000` |
| `/svc/vision/*` | `http://edge-vision-inference:8000` |
| `/svc/sync/*` | `http://edge-sync-forwarder:3000` |
| `/svc/ops/*` | `http://edge-observability-agent:3000` |
| `/svc/policy/*` | `http://edge-policy-sync:3000` |
| `/svc/janitor/*` | `http://edge-retention-janitor:3000` |
| `/svc/feed/*` | `http://edge-feed-intake:5109` |

## Notes

- Compose uses port `5113`.
- Standalone Vite development uses port `5110`.
- If MQTT shows offline in the UI, verify `edge-mqtt-broker` is running and reachable on port `5100`.
