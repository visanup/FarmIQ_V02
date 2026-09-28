# Runbook 08 — PoC: IoT หนึ่งเครื่อง, Edge และ Cloud อีกเครื่อง

ใช้ network ตาม runbook 03 ที่มีอยู่:

| เครื่อง | Wi-Fi | หน้าที่ |
|---|---:|---|
| Edge/Cloud | `192.168.1.120` | Docker Edge + Cloud |
| IoT | `192.168.1.121` | Docker IoT, USB scale, camera Ethernet |
| IoT Ethernet | `192.168.1.122/32` | camera only |
| CCTV Left / Right | `.199` / `.200` | RTSP |

ก่อนเริ่ม ต้องผ่าน routing, camera และ Internet checks ใน `03_FarmIQ Network Configuration Runbook.html`.
Edge/Cloud และ IoT ใช้ repository version เดียวกันที่ `/srv/FarmIQ_V02`.

## A. Edge/Cloud machine — build และเปิด Cloud/Edge

```bash
cd /srv/FarmIQ_V02
docker version
docker compose version
docker network inspect farmiq-net >/dev/null 2>&1 || docker network create farmiq-net

docker build -f edge-layer/edge-vision-inference/Dockerfile.shadow \
  -t farmiq-allocation-shadow:local edge-layer/edge-vision-inference

source cloud-layer/cloud-ml-model-service/ml_weight_prediction/shadow-integration/prepare.sh
export CLOUD_AUTH_MODE=api_key
export CLOUD_API_KEYS=edge-local-key
export INTERNAL_SERVICE_TOKEN=farmiq-internal-dev-token

docker compose -p farmiq-cloud \
  -f cloud-layer/docker-compose.yml \
  -f cloud-layer/docker-compose.dev.yml \
  -f runbook/compose/cloud.local.yml \
  --profile ui up -d --build
```

เมื่อ Cloud healthy แล้ว:

```bash
export EDGE_TENANT_ID=t-001
export EDGE_SITE_ID=st-01
export MODEL_CONTROL_TOKEN=t-001
export EDGE_CLOUD_TOKEN=''
export EDGE_CONTEXTS='[{"tenantId":"t-001","farmId":"f-001","barnId":"b-001","siteId":"st-01"}]'
export CLOUD_AUTH_MODE=api_key
export CLOUD_API_KEY=edge-local-key
export CLOUD_INGESTION_URL=http://host.docker.internal:5122/api/v1/edge/batch
export ALLOCATION_SHADOW_ENABLED=true

docker compose -p farmiq-edge \
  -f edge-layer/docker-compose.yml \
  -f edge-layer/docker-compose.dev.yml \
  -f runbook/compose/edge.shadow.yml \
  up -d --build
```

ตรวจ health บนเครื่องนี้:

```bash
curl -fsS http://127.0.0.1:5125/api/health
curl -fsS http://127.0.0.1:5107/api/ready
curl -fsS http://127.0.0.1:5105/api/health
```

## B. IoT machine — network และ IoT core

บน IoT machine ให้ยืนยันก่อนว่า endpoint ถึง Edge/Cloud:

```bash
ping -c 4 192.168.1.120
curl -fsS http://192.168.1.120:5107/api/ready
nc -vz 192.168.1.120 5100
ip route get 192.168.1.199
ip route get 192.168.1.200
ls -l /dev/ttyUSB0
```

เปิด core ก่อน; service ใน container จะเรียก Edge ผ่าน `192.168.1.120`:

```bash
cd /srv/FarmIQ_V02
export IOT_EDGE_HOST=192.168.1.120

docker compose -p farmiq-iot \
  -f iot-layer/docker-compose.yml \
  -f runbook/compose/iot.endpoints.yml \
  up -d --build ui-app weight-vision-calibrator weight-vision-service

docker compose -p farmiq-iot \
  -f iot-layer/docker-compose.yml \
  -f runbook/compose/iot.endpoints.yml ps
```

เมื่อ mock ผ่านและ camera/scale พร้อม จึงเปิด capture จริง:

```bash
docker compose -p farmiq-iot \
  -f iot-layer/docker-compose.yml \
  -f runbook/compose/iot.endpoints.yml \
  --profile capture up -d --build weight-vision-capture
```

## C. Mock capture จาก IoT machine

runbook เดิมมี `inject-mock-capture.ps1`; บน Ubuntu ต้องติดตั้ง PowerShell 7 (`pwsh`)
ก่อนใช้คำสั่งนี้. Script จะ clone metadata/image เพื่อไม่ใช้ session เดิมซ้ำ:

```bash
cd /srv/FarmIQ_V02
sample="$(find iot-layer/weight-vision-capture/data/metadata -maxdepth 1 -type f | head -n 1)"

pwsh -File iot-layer/scripts/inject-mock-capture.ps1 \
  -SourceMetadataPath "$sample" \
  -TenantId t-001 -FarmId f-001 -BarnId b-001 -DeviceId wv-001 -StationId st-01 \
  -EdgeMediaStoreBaseUrl http://192.168.1.120:5106 \
  -EdgeSessionBaseUrl http://192.168.1.120:5105 \
  -EdgeVisionInferenceBaseUrl http://192.168.1.120:5107 \
  -MqttHosts 192.168.1.120:5100 \
  -MediaUploadHost 192.168.1.120:9000
```

ใช้ session ID ที่ script คืนมาเพื่อตรวจจากเครื่อง IoT:

```bash
curl -fsS 'http://192.168.1.120:5105/api/v1/weighvision/sessions/<sessionId>?tenantId=t-001'
curl -fsS 'http://192.168.1.120:5125/api/v1/weighvision/sessions/<sessionId>?tenantId=t-001'
```

## D. ตรวจ allocation จาก Edge/Cloud machine

```bash
cd /srv/FarmIQ_V02
docker compose -p farmiq-edge \
  -f edge-layer/docker-compose.yml \
  -f edge-layer/docker-compose.dev.yml \
  -f runbook/compose/edge.shadow.yml \
  exec postgres psql -U farmiq -d farmiq -c \
  "SELECT session_id, capture_id, model_version, delivery_status, created_at FROM allocation_shadow_events ORDER BY created_at DESC LIMIT 10;"
```

`held_shadow` คือผลที่ถูกต้องใน PoC นี้. ห้ามนำ allocation ไปใช้น้ำหนักรายตัว
หรือ decision flow; model ปัจจุบันเป็น weak model เพื่อทดสอบ integration.

## E. หยุด stack

บน IoT machine:

```bash
docker compose -p farmiq-iot -f iot-layer/docker-compose.yml -f runbook/compose/iot.endpoints.yml down
```

บน Edge/Cloud machine:

```bash
docker compose -p farmiq-edge -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml -f runbook/compose/edge.shadow.yml down
docker compose -p farmiq-cloud -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.dev.yml -f runbook/compose/cloud.local.yml --profile ui down
```
