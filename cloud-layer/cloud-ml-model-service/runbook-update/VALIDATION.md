# Validation and acceptance for runbook 07/08

## Performed locally on 2026-09-21

- `edge-vision-inference`: 15 XGBoost/shadow/PostgreSQL tests passed.
- Existing scalar inference/database/job regression: 13 tests passed with shadow disabled.
- Shared TypeScript contracts: build passed; 10 tests passed.
- Isolated Docker shadow environment was healthy. HTTP success produced two allocations
  summing to 800 g; invalid scale produced `REJECTED_QUALITY` and no bird rows.
- `docker compose config --quiet` passed for Cloud base + dev + `cloud.local.yml`
  and Edge base + dev + `edge.shadow.yml`, after preparing the manifest checksum.

## Required validation on each target before `up -d --build`

Run exactly with the same `-p`, `-f`, profiles and environment variables that will
be used for `up`:

```bash
docker compose -p <project> -f <base> -f <override> config --quiet
docker compose -p <project> -f <base> -f <override> config --services
```

The IoT configuration cannot be rendered unless its required local env files exist:
`iot-layer/.env` and `iot-layer/weight-vision-service/.env`. This repository copy
contains only `.env.example` for the service, intentionally; use the preserved
site values and verify them before starting capture.

## Database behavior

The normal Cloud services run their own Prisma migration/start behavior. Do not run
`prisma migrate dev`, database reset or seed commands for this runbook.
The XGBoost addition creates only `allocation_shadow_events` and
`session_bird_allocations` in the database configured for `edge-vision-inference`.
With base + dev compose that is the Edge PostgreSQL database named `${POSTGRES_DB}`
(default `farmiq`). Apply `edge-layer/edge-vision-inference/app/allocation_shadow.sql`
as the DB owner before startup if the app role cannot create schemas and indexes.

## Known requirement

Builds need Internet access for package downloads unless Docker build cache or
prebuilt images are already present. The older HTML update guides use `docker load`
for offline deployment; this runbook intentionally uses `--build` as requested.
