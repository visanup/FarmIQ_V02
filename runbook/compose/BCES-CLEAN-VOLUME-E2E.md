# BCES clean-volume E2E runbook

## Production safety boundary

Runbook นี้ใช้เฉพาะ local Docker Desktop. ห้ามใช้ Production URL, credential,
database, queue, object storage หรือ Compose project ในคำสั่งด้านล่าง. Cloud และ Edge
ต้องใช้ volumes/network ที่ขึ้นต้น `bces-e2e-` เท่านั้น.

Create the shared isolated network once:

The Edge session producer and sync-forwarder intentionally share the `farmiq`
database inside `bces-e2e-edge-postgres`. This is the transactional outbox
boundary; every E2E database and volume remains isolated from non-E2E stacks.

```powershell
docker network create bces-e2e-net
```

Start the Cloud minimum set:

```powershell
Set-Location E:\FarmIQ_V02\cloud-layer
docker compose -p bces-e2e-cloud -f docker-compose.yml -f docker-compose.dev.yml -f ..\runbook\compose\cloud.bces-e2e.override.yml up -d postgres rabbitmq cloud-identity-access cloud-tenant-registry cloud-ingestion cloud-weighvision-readmodel cloud-api-gateway-bff dashboard-web
```

Start the Edge minimum set:

```powershell
Set-Location E:\FarmIQ_V02\edge-layer
docker compose -p bces-e2e-edge -f docker-compose.yml -f docker-compose.dev.yml -f ..\runbook\compose\edge.bces-e2e.override.yml up -d postgres minio edge-policy-sync edge-weighvision-session edge-media-store edge-vision-inference edge-sync-forwarder
```

Use BFF `5525`, Dashboard `5542`, policy sync `5509`, session `5505`, media
store `5506`, inference `5507`, and sync forwarder `5508`.

## Manual mock IoT capture

Use the existing `vision-input-mock` image only on the isolated E2E network.
It submits its built-in 1x1 JPEG to Edge inference; it does not contact a
camera, dev stack, or Production system.

```powershell
docker run -d --name bces-e2e-iot-vision-input-mock --network bces-e2e-net -p 5510:3000 `
  -e VISION_INFERENCE_URL=http://bces-e2e-edge-vision-inference:8000 `
  -e AUTO_SUBMIT_ENABLED=false `
  -e MINIO_ENDPOINT=http://bces-e2e-edge-minio:9000 `
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin `
  -e MINIO_BUCKET=bces-e2e-iot-captures farmiq-vision-input-mock:dev
```

Create the scoped Edge session first, then submit the capture with the same
`sessionId`. The session service resolves Batch context from policy cache; the
mock never supplies `batchId`.

Only tear down the E2E projects and their named `bces-e2e-*` volumes after the
test evidence has been retained. Do not run a volume cleanup against the dev projects.
