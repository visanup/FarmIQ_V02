# Runbook 07 — Dev: IoT, Edge และ Cloud บนเครื่องเดียว

ใช้เมื่อ repository อยู่ที่ `E:\FarmIQ_V02` และ Docker Desktop ทำงานอยู่บนเครื่องเดียวกัน
ทุก layer. ขั้นตอนนี้ build จาก source ปัจจุบันและเปิด XGBoost allocation แบบ shadow
โดยข้อมูล allocation ไม่ถูกส่งไป Cloud หรือ decision flow.

## ก่อนเริ่ม

เปิด PowerShell ใหม่ที่ `E:\FarmIQ_V02` แล้วตรวจ Docker:

```powershell
Set-Location E:\FarmIQ_V02
docker version
docker compose version
docker network inspect farmiq-net *> $null
if ($LASTEXITCODE -ne 0) { docker network create farmiq-net }
```

ต้องใช้ Docker Compose 2.24.4 ขึ้นไป เพราะ override ใช้ `!override`.
หากมี stack เก่าอยู่แล้ว ให้ใช้ project name เดิมในคำสั่งด้านล่างและตรวจ
`docker compose ... ps` ก่อน. ห้ามใช้ `down -v` เพราะลบ volumes และข้อมูล.

หากเป็นเครื่องใหม่ ให้สร้างไฟล์ environment ของ IoT จาก template ก่อน. ไฟล์ที่สร้าง
เป็นการตั้งค่าสำหรับ Dev เท่านั้น; ปรับค่า device, RTSP และ scale ตามเครื่องก่อนเปิด
profile `capture`.

```powershell
Copy-Item .\iot-layer\env.example .\iot-layer\.env
Copy-Item .\iot-layer\weight-vision-service\.env.example .\iot-layer\weight-vision-service\.env
```

## 1. สร้าง Edge shadow image และ package

```powershell
docker build -f .\edge-layer\edge-vision-inference\Dockerfile.shadow `
  -t farmiq-allocation-shadow:local `
  .\edge-layer\edge-vision-inference

Set-Location .\cloud-layer\cloud-ml-model-service
. .\ml_weight_prediction\shadow-integration\prepare.ps1
Set-Location E:\FarmIQ_V02
```

คำสั่งสุดท้ายต้องแสดง manifest SHA256. เก็บค่านี้ไว้ตลอด shell ที่จะยก Edge stack.
package ถูก mount read-only จาก
`cloud-layer/cloud-ml-model-service/ml_weight_prediction/artifacts/shadow-package-approved`.

## 2. สร้างและเปิด Cloud

```powershell
$env:CLOUD_AUTH_MODE = 'api_key'
$env:CLOUD_API_KEYS = 'edge-local-key'
$env:INTERNAL_SERVICE_TOKEN = 'farmiq-internal-dev-token'

docker compose -p farmiq-cloud `
  -f .\cloud-layer\docker-compose.yml `
  -f .\cloud-layer\docker-compose.dev.yml `
  -f .\runbook\compose\cloud.local.yml `
  --profile ui up -d --build
```

`cloud.local.yml` ย้าย cloud-hybrid-router ไป host port `5149`; port `5141`
ยังสงวนให้ PostgreSQL ของ Edge. สำหรับเครื่อง Dev ที่รวมทุก layer ไฟล์ override นี้
ตั้ง `cloud-advanced-analytics` เป็น **mock service** โดยใช้
`cloud-advanced-analytics/Dockerfile.mock` แทน Dockerfile ปกติ เพื่อให้ service
อื่นที่พึ่งพา endpoint นี้ start และผ่าน health check ได้ โดยไม่ดาวน์โหลดหรือ build
Python ML/statistics stack และไม่โหลด model จริง. Mock เปิดที่ `http://localhost:5146`
และตอบ `GET /api/health` ด้วย HTTP 200. ใช้ได้เฉพาะ Dev; ห้ามใช้ใน QA, UAT,
Staging หรือ Production. รอให้ Cloud startup ก่อนทำขั้นตอน Edge.

## 3. สร้างและเปิด Edge พร้อม shadow

สร้าง production artifact ของ Edge Ops Web ก่อน เพราะ Dockerfile ของ service นี้
ใช้ `edge-ops-web/dist` เป็น build context:

```powershell
npm --prefix .\edge-layer\edge-ops-web run build
```

```powershell
$env:EDGE_TENANT_ID = 't-001'
$env:EDGE_SITE_ID = 'st-01'
$env:MODEL_CONTROL_TOKEN = 't-001'
$env:EDGE_CLOUD_TOKEN = ''
$env:EDGE_CONTEXTS = '[{"tenantId":"t-001","farmId":"f-001","barnId":"b-001","siteId":"st-01"}]'
$env:CLOUD_AUTH_MODE = 'api_key'
$env:CLOUD_API_KEY = 'edge-local-key'
$env:CLOUD_INGESTION_URL = 'http://host.docker.internal:5122/api/v1/edge/batch'
$env:ALLOCATION_SHADOW_ENABLED = 'true'

docker compose -p farmiq-edge `
  -f .\edge-layer\docker-compose.yml `
  -f .\edge-layer\docker-compose.dev.yml `
  -f .\runbook\compose\edge.shadow.yml `
  up -d --build
```

## 4. สร้างและเปิด IoT core

IoT containers ใช้ `host.docker.internal` เพื่อเรียก published Edge ports บนเครื่องเดียวกัน.

```powershell
$env:IOT_EDGE_HOST = 'host.docker.internal'

docker compose -p farmiq-iot `
  -f .\iot-layer\docker-compose.yml `
  -f .\runbook\compose\iot.endpoints.yml `
  up -d --build ui-app weight-vision-calibrator weight-vision-service
```

ยังไม่เปิด `weight-vision-capture` จนกว่าจะตรวจ mock สำเร็จ. เมื่อพร้อมต่อกล้องและ
scale จริง ให้เพิ่ม `--profile capture` และ service `weight-vision-capture`.

## 5. ตรวจสถานะ

```powershell
docker compose -p farmiq-cloud -f .\cloud-layer\docker-compose.yml -f .\cloud-layer\docker-compose.dev.yml -f .\runbook\compose\cloud.local.yml --profile ui ps
docker compose -p farmiq-edge -f .\edge-layer\docker-compose.yml -f .\edge-layer\docker-compose.dev.yml -f .\runbook\compose\edge.shadow.yml ps
docker compose -p farmiq-iot -f .\iot-layer\docker-compose.yml -f .\runbook\compose\iot.endpoints.yml ps

Invoke-WebRequest http://localhost:5125/api/health -UseBasicParsing
Invoke-WebRequest http://localhost:5146/api/health -UseBasicParsing # Advanced Analytics mock (Dev only)
Invoke-WebRequest http://localhost:5107/api/ready -UseBasicParsing
Invoke-WebRequest http://localhost:5105/api/health -UseBasicParsing
```

ถ้า Edge 5107 ไม่ ready ให้ดู:

```powershell
docker compose -p farmiq-edge -f .\edge-layer\docker-compose.yml -f .\edge-layer\docker-compose.dev.yml -f .\runbook\compose\edge.shadow.yml logs --tail=200 edge-vision-inference
```

## 6. Vision Input Mock — Dev only

`vision-input-mock` สร้างภาพและ metadata จำลอง แล้วส่งเข้า
`edge-vision-inference` ทุก 60 วินาที เพื่อทดสอบเส้นทาง Media Store, Session
Metadata และ inference โดยไม่ต้องต่อกล้องหรืออุปกรณ์จริง.

**ข้อจำกัดบังคับ:** ใช้ได้เฉพาะเครื่อง Dev เท่านั้น. ห้าม build, deploy, หรือเปิด
service นี้ใน QA, UAT, Staging หรือ Production และห้ามนำผล prediction จาก mock
ไปใช้เป็นข้อมูลปฏิบัติการหรือ decision flow.

เริ่มเฉพาะเมื่อ `edge-vision-inference` และ Edge PostgreSQL พร้อมแล้ว:

```powershell
Set-Location E:\FarmIQ_V02\cloud-layer\cloud-ml-model-service\vision-input-mock
docker compose -p farmiq-vision-input-mock up -d --build
```

ตรวจผลจาก log หรือ API ของ Vision:

```powershell
docker compose -p farmiq-vision-input-mock logs --tail=50
Invoke-RestMethod 'http://127.0.0.1:5107/api/v1/inference/results?sessionId=mock-periodic-session'
```

หยุดและลบเฉพาะ mock service โดยไม่กระทบ Edge stack:

```powershell
docker compose -p farmiq-vision-input-mock down
```

## 7. ยิง mock capture จาก host

ใช้ PowerShell script เดิมจาก host; endpoint จึงเป็น `127.0.0.1` ไม่ใช่
`host.docker.internal`. เลือก metadata จริงที่ต้องการ replay:

```powershell
$sample = Get-ChildItem .\iot-layer\weight-vision-capture\data\metadata -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

powershell -ExecutionPolicy Bypass -File .\iot-layer\scripts\inject-mock-capture.ps1 `
  -SourceMetadataPath $sample `
  -TenantId 't-001' -FarmId 'f-001' -BarnId 'b-001' -DeviceId 'wv-001' -StationId 'st-01' `
  -EdgeMediaStoreBaseUrl 'http://127.0.0.1:5106' `
  -EdgeSessionBaseUrl 'http://127.0.0.1:5105' `
  -EdgeVisionInferenceBaseUrl 'http://127.0.0.1:5107' `
  -MqttHosts '127.0.0.1:5100' `
  -MediaUploadHost '127.0.0.1:9000'
```

ตรวจ session ID ที่ output กลับมา:

```powershell
Invoke-RestMethod 'http://127.0.0.1:5105/api/v1/weighvision/sessions/<sessionId>?tenantId=t-001' | ConvertTo-Json -Depth 12
Invoke-RestMethod 'http://127.0.0.1:5125/api/v1/weighvision/sessions/<sessionId>?tenantId=t-001' | ConvertTo-Json -Depth 12
```

ให้รอ Cloud readmodel สักครู่หาก endpoint ตอบ 404 ครั้งแรก.

## 8. ตรวจ shadow allocation

```powershell
docker compose -p farmiq-edge -f .\edge-layer\docker-compose.yml -f .\edge-layer\docker-compose.dev.yml -f .\runbook\compose\edge.shadow.yml logs --tail=200 edge-vision-inference

docker compose -p farmiq-edge -f .\edge-layer\docker-compose.yml -f .\edge-layer\docker-compose.dev.yml -f .\runbook\compose\edge.shadow.yml exec postgres `
  psql -U farmiq -d farmiq -c "SELECT session_id, capture_id, model_version, delivery_status, created_at FROM allocation_shadow_events ORDER BY created_at DESC LIMIT 10;"
```

ผลที่ถูกต้อง: scalar job เดิม complete, allocation ที่ผ่านคุณภาพมี `WEAK_ALLOCATION`,
ข้อมูลไม่ครบหรือ scale ไม่ stable เป็น `REJECTED_QUALITY`, และทุก event เป็น `held_shadow`.

## 9. หยุดเฉพาะ stack

```powershell
docker compose -p farmiq-iot -f .\iot-layer\docker-compose.yml -f .\runbook\compose\iot.endpoints.yml down
docker compose -p farmiq-edge -f .\edge-layer\docker-compose.yml -f .\edge-layer\docker-compose.dev.yml -f .\runbook\compose\edge.shadow.yml down
docker compose -p farmiq-cloud -f .\cloud-layer\docker-compose.yml -f .\cloud-layer\docker-compose.dev.yml -f .\runbook\compose\cloud.local.yml --profile ui down
```
