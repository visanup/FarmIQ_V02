Purpose: Expected verification evidence for the current local edge compose path.  
Scope: Commands and expected signals, not historical screenshots.  
Owner: FarmIQ Edge Team  
Last updated: 2026-07-16

---

## Compose status

Command:

```bash
cd edge-layer
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
```

Expected signals:

- `postgres` is `healthy`
- core HTTP services are `healthy`
- `edge-ops-web` is `healthy`
- `edge-cloud-ingestion-mock` is running when local sync uses the mock endpoint

---

## Browser entrypoint

Command:

```bash
curl -I http://localhost:5113/
curl http://localhost:5113/api/health
```

Expected:

- `HTTP/1.1 200 OK`
- `{"status":"ok"}`

---

## Aggregated edge status

Command:

```bash
curl http://localhost:5111/api/v1/ops/edge/status
```

Expected:

- JSON with overall status
- service list
- resource summary
- sync summary

---

## Sync forwarder state

Command:

```bash
curl http://localhost:5108/api/v1/sync/state
```

Expected:

- JSON payload with pending, claimed, acked, failed, and DLQ counters

---

## Vision health

Command:

```bash
curl http://localhost:5107/api/health
curl http://localhost:5107/api/ready
```

Expected:

- health endpoint returns healthy
- readiness endpoint confirms dependency readiness
