# BCES clean-volume E2E runbook

## วัตถุประสงค์และ safety boundary

Runbook นี้ใช้ยืนยัน BCES-001 ถึง BCES-007 บน local Docker Desktop โดยไม่แตะ
dev/production. ทุก container, network และ named volume ต้องขึ้นต้น
`bces-e2e-`. ห้ามใช้ Production URL/credential, `prisma migrate reset`,
`synchronize(true)` หรือ integration test ที่ทำลาย schema กับฐาน `farmiq`.

Service ขั้นต่ำ:

- Cloud: PostgreSQL, RabbitMQ, Identity, Tenant Registry, Ingestion,
  WeighVision Read-model, BFF และ Dashboard
- Edge: PostgreSQL, MinIO, Policy Sync, WeighVision Session, Media Store,
  Vision Inference และ Sync Forwarder
- mock IoT: `vision-input-mock` โดยปิด periodic auto-submit

พอร์ต: BFF `5525`, Dashboard `5542`, session `5505`, media store `5506`,
inference `5507`, forwarder `5508`, policy sync `5509`, mock IoT `5510`,
Cloud PostgreSQL `5540`, Edge PostgreSQL `5541`.

## 1. Preflight

```powershell
docker version
docker network ls --filter name=^bces-e2e-net$
docker volume ls --filter name=^bces-e2e-
docker ps -a --filter name=bces-e2e
```

สร้าง network เมื่อยังไม่มีเท่านั้น:

```powershell
docker network create bces-e2e-net
```

ตรวจ Compose merge ก่อน start. Edge override บังคับ token จึงใช้ placeholder ได้
เฉพาะคำสั่ง `config`; ห้ามใช้ placeholder start service.

```powershell
Set-Location E:\FarmIQ_V02\cloud-layer
docker compose -p bces-e2e-cloud -f docker-compose.yml -f docker-compose.dev.yml `
  -f ..\runbook\compose\cloud.bces-e2e.override.yml config --quiet

Set-Location E:\FarmIQ_V02\edge-layer
$env:BCES_EDGE_CLOUD_TOKEN = 'config-validation-only'
docker compose -p bces-e2e-edge -f docker-compose.yml -f docker-compose.dev.yml `
  -f ..\runbook\compose\edge.bces-e2e.override.yml config --quiet
Remove-Item Env:BCES_EDGE_CLOUD_TOKEN
```

## 2. Start Cloud และสร้าง short-lived Edge credential

```powershell
Set-Location E:\FarmIQ_V02\cloud-layer
docker compose -p bces-e2e-cloud -f docker-compose.yml -f docker-compose.dev.yml `
  -f ..\runbook\compose\cloud.bces-e2e.override.yml up -d `
  postgres rabbitmq cloud-identity-access cloud-tenant-registry cloud-ingestion `
  cloud-weighvision-readmodel cloud-api-gateway-bff dashboard-web
```

รอ health แล้วสร้าง JWT อายุ 1 ชั่วโมงจาก BFF container ของ E2E เท่านั้น. Token
ต้องมี tenant/site scope และ role `edge_service`; ห้าม commit token ลงไฟล์.

```powershell
$env:BCES_EDGE_CLOUD_TOKEN = docker exec bces-e2e-cloud-bff node -e `
  "const jwt=require('jsonwebtoken'); console.log(jwt.sign({sub:'bces-e2e-edge',roles:['edge_service'],tenant_id:'t-001',site_id:'site-e2e'},process.env.JWT_SECRET,{audience:'farmiq-api',issuer:'farmiq',expiresIn:'1h'}))"
if ([string]::IsNullOrWhiteSpace($env:BCES_EDGE_CLOUD_TOKEN)) { throw 'JWT generation failed' }
```

## 3. Start Edge minimum stack

```powershell
Set-Location E:\FarmIQ_V02\edge-layer
docker compose -p bces-e2e-edge -f docker-compose.yml -f docker-compose.dev.yml `
  -f ..\runbook\compose\edge.bces-e2e.override.yml up -d `
  postgres minio edge-policy-sync edge-weighvision-session edge-media-store `
  edge-vision-inference edge-sync-forwarder
```

ตรวจว่า containers ที่จำเป็น healthy:

```powershell
docker ps --filter name=bces-e2e --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

หาก inference เริ่มพร้อม PostgreSQL แล้วล้มด้วย `database system is starting up`
ให้รอ Edge PostgreSQL healthy แล้ว restart เฉพาะ
`bces-e2e-edge-vision-inference`. หาก Tenant Registry connection pool timeout
ให้ตรวจ Cloud PostgreSQL ก่อน แล้ว restart เฉพาะ
`bces-e2e-cloud-tenant-registry`; ห้าม restart dev stack.

## 4. Disposable database สำหรับ sync-forwarder integration

Test `multiReplica.test.ts` มี `synchronize(true)` และต้องใช้ explicit
`TEST_DATABASE_URL` เท่านั้น. Source test ปัจจุบันไม่มี fallback ไป
`DATABASE_URL`.

```powershell
docker exec bces-e2e-edge-postgres psql -U farmiq -d postgres -c `
  'CREATE DATABASE edge_sync_forwarder_test'
$env:TEST_DATABASE_URL = 'postgresql://farmiq:farmiq_dev@127.0.0.1:5541/edge_sync_forwarder_test'
```

ถ้าฐานมีอยู่แล้ว ให้ใช้ชื่อ disposable ใหม่หรือ drop/recreate เฉพาะชื่อ
`edge_sync_forwarder_test` หลังตรวจชื่อเป้าหมาย. ห้ามชี้ test ไป `farmiq`,
`edge_vision_inference` หรือฐาน dev/production.

## 5. Start mock IoT

ใช้ cached image กับ source mount read-only เพื่อทดสอบโค้ดปัจจุบันโดยไม่ต้อง pull
base image. ก่อน remove container ให้ยืนยันชื่อ exact match.

```powershell
docker ps -a --filter name=^bces-e2e-iot-vision-input-mock$ --format '{{.Names}}'
docker rm -f bces-e2e-iot-vision-input-mock 2>$null
docker run -d --name bces-e2e-iot-vision-input-mock --network bces-e2e-net `
  -p 5510:3000 `
  --mount type=bind,source=E:\FarmIQ_V02\cloud-layer\cloud-ml-model-service\vision-input-mock\app.py,target=/app/app.py,readonly `
  -e VISION_INFERENCE_URL=http://bces-e2e-edge-vision-inference:8000 `
  -e MEDIA_STORE_URL=http://bces-e2e-edge-media-store:3000 `
  -e AUTO_SUBMIT_ENABLED=false `
  -e MINIO_ENDPOINT=http://bces-e2e-edge-minio:9000 `
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin `
  -e MINIO_BUCKET=farmiq-media farmiq-vision-input-mock:dev
```

## 6. Realtime E2E

สร้าง session ด้วย physical scope เท่านั้น. ห้ามส่ง `batchId`; Edge ต้อง resolve
จาก policy cache และ stamp immutable context.

```powershell
$sessionId = 'bces-e2e-' + ([guid]::NewGuid().ToString('N').Substring(0,12))
$sessionBody = @{
  sessionId=$sessionId; tenantId='t-001'; farmId='f-001'; barnId='b-001'
  deviceId='wv-001'; stationId='st-001'
} | ConvertTo-Json
$session = Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:5505/api/v1/weighvision/sessions' `
  -ContentType 'application/json' -Body $sessionBody
$session | ConvertTo-Json -Depth 10
```

Expected: `batchId=batch-e2e-t001`, `stationId=st-001`, resolution `resolved` และ
revision มากกว่าศูนย์.

```powershell
$captureBody = @{
  tenantId='t-001'; farmId='f-001'; barnId='b-001'
  deviceId='wv-001'; stationId='st-001'; sessionId=$sessionId
  occurredAt=(Get-Date).ToUniversalTime().ToString('o')
  normalizedFeatures=@{area_mm2=12000;confidence_score=0.95;distance_mm=420;roi_count=1;detection_count=1}
  rawMetadata=@{height_estimation=@{floor_depth_mm=420}}
} | ConvertTo-Json -Depth 6
$capture = Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:5510/api/v1/mock/captures' `
  -ContentType 'application/json' -Body $captureBody
$capture | ConvertTo-Json -Depth 10
Start-Sleep -Seconds 5
$edgeResult = Invoke-RestMethod `
  -Uri "http://127.0.0.1:5507/api/v1/inference/results?sessionId=$sessionId" `
  -Headers @{'x-tenant-id'='t-001'}
$edgeResult | ConvertTo-Json -Depth 20
```

Expected: `count=1`; metadata มี Batch, breed, age, model policy,
`prediction_mode` และ fallback reason. ถ้า count เป็น 2 ให้ตรวจว่า mock รุ่นเก่า
ยัง POST inference ซ้ำหลัง media-store auto-trigger.

รอ forwarder แล้วตรวจ Cloud BFF:

```powershell
Start-Sleep -Seconds 8
$login = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:5525/api/v1/auth/login' `
  -ContentType 'application/json' `
  -Body (@{email='admin@farmiq.com';password='password123'} | ConvertTo-Json)
$headers = @{Authorization="Bearer $($login.access_token)"}
$cloud = Invoke-RestMethod -Headers $headers `
  -Uri 'http://127.0.0.1:5525/api/v1/weighvision/sessions?tenantId=t-001&farmId=f-001&barnId=b-001&limit=100'
$cloud.items | Where-Object sessionId -eq $sessionId | ConvertTo-Json -Depth 20
```

Expected: มี session เดียวกันและ inference provenance ครบ.

## 7. Dashboard validation

Dashboard override mount `apps/dashboard-web/build` read-only. หลังแก้ UI:

```powershell
Set-Location E:\FarmIQ_V02\apps\dashboard-web
& 'C:\Program Files\nodejs\npm.cmd' run build
Set-Location E:\FarmIQ_V02\cloud-layer
docker compose -p bces-e2e-cloud -f docker-compose.yml -f docker-compose.dev.yml `
  -f ..\runbook\compose\cloud.bces-e2e.override.yml up -d --no-deps dashboard-web
```

เปิด `http://127.0.0.1:5542`, login ด้วย dev seed แล้วเลือก
`t-001/f-001/b-001`. หน้า WeighVision Sessions ต้องแสดง Station, Batch,
breed/age, weight, prediction mode และ fallback. หน้า detail ต้องแสดง provenance
เดียวกับ BFF. Unassigned session ต้องแสดง reason/แนวทาง bind ไม่ใช่ช่องว่าง.

## 8. Historical reprocess validation

ก่อน enqueue ต้อง preview และ confirm scope/interval ผ่าน BFF; confirm association
ต้องไม่สร้าง inference. Reprocess ต้องเปิดเฉพาะ E2E ด้วย
`HISTORICAL_REPROCESS_ENABLED=true`, media retained และ queue
`historical-reprocess` แยกจาก realtime.

Validation query สำหรับ lineage:

```powershell
docker exec bces-e2e-cloud-postgres psql -U farmiq `
  -d cloud_weighvision_readmodel -c `
  'SELECT r."sessionId",r."inferenceId",r."originalInferenceId",r."historicalJobId",r.revision FROM weighvision_inference_revision r ORDER BY r."createdAt" DESC;'
```

ยืนยัน original และ revision ยังอยู่:

```sql
SELECT r."sessionId", r."inferenceId", r."originalInferenceId", r.revision,
       EXISTS(SELECT 1 FROM weighvision_inference i
              WHERE i.id=r."originalInferenceId") AS original_still_exists,
       EXISTS(SELECT 1 FROM weighvision_inference i
              WHERE i.id=r."inferenceId") AS revision_still_exists
FROM weighvision_inference_revision r;
```

Expected: ทั้งสองค่าเป็น `true`. ทดสอบ controlled backlog ต้องเห็น historical
pause เมื่อ realtime active, cancel เฉพาะ queued job และ resume job ที่ pause ได้.

## 9. Troubleshooting

- `database system is starting up`: รอ PostgreSQL healthy และ restart เฉพาะ
  service E2E ที่ล้มจาก startup race.
- Prisma client เก่า/file lock: generate/build ภายใน isolated container; ไม่เขียน
  `dist` ที่ host ซึ่ง bind mount อยู่.
- Tenant Registry pool timeout: ตรวจ Cloud PostgreSQL/connection count ก่อน restart
  Tenant Registry E2E เพียงตัวเดียว.
- Docker Hub metadata timeout: ใช้ cached image/source bind mount; บันทึกว่า image
  rebuild ไม่ได้ยืนยันในรอบนั้น.
- Dashboard แสดง empty ทั้งที่ BFF มีข้อมูล: ห้าม seed React Query ด้วย
  `initialData: []`; rebuild Vite artifact แล้ว hard reload.
- Notification 502 ใน minimum stack: notification service ไม่อยู่ใน BCES scope;
  WeighVision API ต้องยังตอบ 200 และ render ได้.
- Policy sync 401/403: สร้าง short-lived JWT ใหม่และตรวจ `tenant_id=t-001`,
  `site_id=site-e2e`, role `edge_service`.

## 10. Rollback และ cleanup

Rollback feature โดยปิด flags/enqueue ใหม่; ห้ามลบ association audit, original
inference หรือ revisions. Cleanup ทำได้เฉพาะหลังเก็บ evidence และต้องตรวจชื่อ
project/volume ก่อนทุกครั้ง:

```powershell
docker ps -a --filter name=bces-e2e
docker volume ls --filter name=^bces-e2e-

Set-Location E:\FarmIQ_V02\edge-layer
docker compose -p bces-e2e-edge -f docker-compose.yml -f docker-compose.dev.yml `
  -f ..\runbook\compose\edge.bces-e2e.override.yml down

Set-Location E:\FarmIQ_V02\cloud-layer
docker compose -p bces-e2e-cloud -f docker-compose.yml -f docker-compose.dev.yml `
  -f ..\runbook\compose\cloud.bces-e2e.override.yml down
```

ไม่ใส่ `-v` เป็นค่าเริ่มต้น. ถ้าต้อง recreate clean volumes ให้ลบเฉพาะ exact
names `bces-e2e-cloud-postgres`, `bces-e2e-edge-postgres` และ
`bces-e2e-edge-minio` หลังตรวจว่าไม่มี dev/production container ใช้อยู่.
