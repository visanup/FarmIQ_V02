# BCES Clean-volume E2E Specification

## วัตถุประสงค์

ทดสอบ BCES-005/006 บนฐานข้อมูลและ storage ว่าง โดยไม่หยุด ลบ หรือใช้ซ้ำ
container, network และ volume ของ FarmIQ dev stack ที่กำลังใช้งานอยู่ และไม่ติดต่อ
Production ไม่ว่ากรณีใด

## ขอบเขตความปลอดภัยต่อ Production

การทดสอบนี้เป็น local-only test environment ไม่ใช่ขั้นตอน deploy. การเปลี่ยนแปลง
ของ BCES จะอยู่ใน source workspace และ Compose project `bces-e2e-*` เท่านั้น จึงไม่
เปลี่ยน image, deployment, database, queue, object storage หรือ credential ของ
Production

- ห้ามใช้ Production hostname, secret, VPN route, database URL, object storage หรือ
  message broker ใน override และตัวแปร environment ของ E2E
- Cloud และ Edge database URL ต้องระบุ container hostname ของ E2E โดยตรง คือ
  `bces-e2e-cloud-postgres` และ `bces-e2e-edge-postgres`; ห้ามใช้ alias `postgres`
  ที่อาจซ้ำกันบน shared network
- Edge credential ต้องเป็น JWT dev อายุสั้นและจำกัด tenant/site ของข้อมูล E2E;
  ห้ามบันทึก Production credential ลง Compose, repository หรือ log
- อนุญาต cleanup เฉพาะทรัพยากรชื่อ `bces-e2e-*` หลังเก็บหลักฐานแล้วเท่านั้น

## Isolation contract

| ทรัพยากร | Dev stack | E2E stack |
|---|---|---|
| Compose project | `cloud-layer`, `edge-layer` | `bces-e2e-cloud`, `bces-e2e-edge` |
| Network | `farmiq-net` | `bces-e2e-net` |
| Cloud PostgreSQL volume | `postgres_data` | `bces-e2e-cloud-postgres` |
| Edge PostgreSQL volume | `edge_postgres_data` | `bces-e2e-edge-postgres` |
| Edge MinIO volume | existing dev volume | `bces-e2e-edge-minio` |
| Container names | `farmiq-*` | `bces-e2e-*` |

Compose override ต้องไม่ inherit `container_name` หรือ host port ของ dev stack
และต้องใช้ `bces-e2e-net` แบบ external เพื่อให้ Cloud กับ Edge projects สื่อสารกันได้

## Minimal services

### Cloud

- PostgreSQL, RabbitMQ
- identity access, tenant registry, ingestion
- WeighVision read-model, API Gateway BFF, Dashboard

### Edge

- PostgreSQL, MinIO
- policy sync, WeighVision session, media store
- vision inference, sync forwarder

ไม่ต้อง start analytics, telemetry, LLM, pgAdmin, Datadog หรือ service อื่นที่ไม่อยู่ใน
Batch Context → inference → read-model path

## Host ports

| Endpoint | E2E port |
|---|---:|
| Cloud PostgreSQL | 5540 |
| Edge PostgreSQL | 5541 |
| Cloud BFF | 5525 |
| Dashboard | 5542 |
| Edge session | 5505 |
| Edge media store | 5506 |
| Edge inference | 5507 |
| Edge sync forwarder | 5508 |
| Edge policy sync | 5509 |

## Required override behaviour

1. Cloud service DNS/URLs ต้องชี้ `bces-e2e-cloud-*` บน `bces-e2e-net`
2. Edge policy sync ต้องเรียก `bces-e2e-cloud-bff:3000`
3. Edge sync forwarder ต้องส่งไป `bces-e2e-cloud-ingestion:3000`
4. เปิด `BATCH_CONTEXT_AUTO_BIND_ENABLED=true` และ
   `BATCH_CONTEXT_INFERENCE_ENABLED=true`
5. migration/seed ทำเฉพาะ database ของ E2E stack
6. ทุก service ต้องใช้ explicit database host ของ layer ตนเอง เพื่อไม่ resolve
   `postgres` ข้าม Cloud/Edge บน shared network
   - ข้อยกเว้นที่ตั้งใจไว้: `edge-weighvision-session` และ
     `edge-sync-forwarder` ใช้ database `farmiq` เดียวกันภายใน
     `bces-e2e-edge-postgres` เพื่อเป็น transactional outbox boundary;
     volume นี้ยังเป็น `bces-e2e-edge-postgres` ที่แยกจาก dev/Production

## Acceptance flow

1. Start minimal Cloud และ Edge stack; health checks ผ่าน
2. Migrate/seed tenant, farm, barn, active Batch, device และ station
3. Bind device/station กับ Batch ผ่าน BFF
4. รอ policy sync ให้ cache ได้ context/revision
5. ส่ง mock image; ตรวจ session เป็น `resolved` และมี immutable provenance
6. ตรวจ inference มี batch, breed, sex, age, station และ fallback/model policy
7. ตรวจ sync เข้า Cloud read-model และ Dashboard แสดง Station, Batch, breed,
   age, prediction mode, weight และ fallback reason
8. บันทึก latency แล้วเปรียบเทียบกับ baseline ก่อนปิด BCES-005/006

## หลักฐานที่ยืนยันแล้ว (2026-09-25)

- minimal Cloud/Edge services ตอบ `/api/health` ครบผ่าน ports E2E
- Cloud tenant registry ถูก migrate/seed ใน volume `bces-e2e-cloud-postgres`
- BFF control API ส่ง batch context ที่มี device/station binding และ fallback policy
  ได้
- `edge-policy-sync` cache และ resolve context จาก
  `tenant + device + station` ได้ใน `bces-e2e-edge-postgres`
- mock IoT capture สร้าง inference job บน `bces-e2e-*` แล้วได้ผล fallback
  `5.16 kg`; event ถูก forward, Cloud read-model และ BFF แสดง batch, station,
  breed, sex, age และ fallback context เดียวกัน

เส้นทาง session → inference → Cloud read-model → Dashboard ยังไม่ถือว่าผ่าน: image
ปัจจุบันของ `edge-weighvision-session` ยังไม่มี HTTP route สำหรับสร้าง session จริง
จึงต้องเพิ่ม route และ E2E automation ก่อนปิด BCES-005/006

## Safety and cleanup

ห้ามใช้ `docker compose down -v` กับ dev project. Cleanup ใช้ได้เฉพาะ
`bces-e2e-cloud`, `bces-e2e-edge`, `bces-e2e-*` volumes และ `bces-e2e-net`
หลังเก็บผลทดสอบเสร็จแล้ว
