# การซิงก์บริบท Batch ไปยัง Edge สำหรับ WeightVision

## วัตถุประสงค์

ทำให้ทุก WeightVision session สามารถระบุ flock ที่กำลังชั่งน้ำหนักได้อย่าง
ตรวจสอบย้อนกลับได้ โดยไม่ให้การ inference แบบ realtime ต้องพึ่งการเรียก
Cloud ทุกครั้ง Session ที่มีบริบทครบต้องแสดง batch, สายพันธุ์, เพศ, อายุเป็นวัน
และ model package ที่ถูกเลือกได้

เอกสารนี้กำหนดพฤติกรรมที่ปลอดภัยสำหรับฟาร์มที่เริ่มชั่งน้ำหนักก่อนบันทึกข้อมูล
Batch & Flocks ด้วย

## สถานะ implementation ที่ตรวจสอบแล้ว (2026-09-25)

Core path ของ Batch Context Sync ถูก implement แล้ว:

- Cloud Tenant Registry มี additive migration สำหรับ batch context revision และ
  transactional outbox; Batch/binding write สร้าง context event สำหรับการ sync
- Cloud BFF และ Tenant Registry เปิด endpoint batch-context snapshot/delta พร้อม
  ETag/revision และตรวจ scope ของ binding
- `edge-policy-sync` เก็บ batch context/device-station binding ใน local cache และ
  expose lookup ให้ Edge session/inference
- Edge WeighVision Session resolve active binding อัตโนมัติ และ stamp context
  revision/resolution/provenance แบบ immutable ลง session
- Edge Vision Inference ใช้ immutable session context เพื่อคำนวณอายุจากเวลา
  capture (หรือเวลาเริ่ม session เมื่อไม่มี capture metadata) และส่ง provenance,
  station scope และ fallback reason กลับ Cloud
- Cloud WeighVision read-model และ Dashboard แสดง Station, Batch Context,
  breed, age, prediction mode และ fallback/model status แล้ว

ได้ทดสอบเส้นทางจริงบน dev volume ที่เก็บข้อมูลเดิมไว้: binding ของ device/station
สร้าง session, inference ได้ `2.94 kg`, `Arbor Acres Plus`, อายุ `16` วัน และ
fallback `NO_SITE_SUBSCRIPTION` ซึ่งปรากฏใน Cloud read-model และ Dashboard

สิ่งที่ยังไม่ปิดเกณฑ์ acceptance ทั้งหมดคือ clean-volume E2E, Playwright critical
path และ performance/latency baseline; BCES-007 (historical association/reprocess)
ยังเป็นงาน optional ที่ไม่ได้ implement.

## พฤติกรรมเป้าหมาย

```text
Dashboard สร้าง/แก้ไข/เปิดใช้งาน Batch
  -> Tenant Registry เขียน Batch + outbox event ใน transaction เดียวกัน
  -> Cloud control endpoint เปิดเผย batch context ล่าสุดให้ Edge site
  -> edge-policy-sync upsert ลง local cache
  -> device/station เริ่ม WeightVision session
  -> Edge resolve active batch หนึ่งรายการและ stamp batchId ลง session
  -> inference อ่าน local context, คำนวณ age_days และเลือก model package
  -> prediction และ provenance ถูก sync กลับ Cloud และแสดงใน Dashboard
```

Cloud เป็นแหล่งข้อมูลหลัก (source of truth) ส่วน Edge เป็น versioned read cache
เพื่อให้ realtime inference ทำงานต่อได้เมื่อ Cloud ติดต่อไม่ได้

## โมเดลข้อมูลและสัญญา API

### Batch context

Edge cache เก็บหนึ่งรายการต่อ binding `tenantId + deviceId + stationId` ซึ่ง
ประกอบด้วย Batch ที่มีผลบังคับใช้และ revision ที่เพิ่มขึ้นอย่างต่อเนื่อง

```json
{
  "eventType": "batch.upsert",
  "eventId": "uuid",
  "revision": 4,
  "tenantId": "t-001",
  "farmId": "f-001",
  "barnId": "b-001",
  "batchId": "uuid",
  "status": "active",
  "species": "broiler",
  "breedCode": "Arbor Acres Plus",
  "sex": "male",
  "startDate": "2026-09-08",
  "deviceBindings": [{ "deviceId": "wv-001", "stationId": "st-01" }],
  "modelPolicy": {
    "packageId": "weight-broiler-arbor-acres-v1",
    "version": "1.0.0"
  }
}
```

คอลัมน์ที่จำเป็นใน cache:

- ขอบเขต: tenant, farm, barn, device, station และ batch
- บริบท ML: species, breed, sex, start date, package และ version
- metadata การ sync: revision, source event ID, เวลาที่ดึง, สถานะ และวันหมดอายุ

### กฎการ resolve

1. ตอนสร้าง session ให้ resolve active cache record ด้วย tenant, device และ
   station โดย farm/barn ต้องตรงกัน
2. Stamp `batchId` และ context version ที่ resolve ได้ลงใน session แบบ immutable
3. คำนวณ `age_days = วันที่ capture ตามเวลาท้องถิ่น - วันเริ่มเลี้ยงของ batch`
4. หากไม่พบ binding ที่ active เพียงหนึ่งรายการ ให้สร้าง session เป็น
   **unassigned** และใช้ fallback model ที่กำหนดไว้โดยชัดเจน
5. หากพบมากกว่าหนึ่ง active binding ให้ปฏิเสธ session ด้วย
   `BATCH_CONTEXT_AMBIGUOUS`; ห้ามเดา flock
6. บันทึก model package/version, batch ID, breed และ age ใน inference provenance

## Lifecycle events

Tenant Registry ต้องเขียน outbox ใน transaction เดียวกับการเขียน Batch รองรับ
event ต่อไปนี้:

- `batch.upsert` — สร้างหรือแก้ไข master data/binding
- `batch.activate` — ใช้กับ Edge session ใหม่ได้
- `batch.deactivate` — ห้ามนำ binding นี้ไปใช้กับ session ใหม่
- `batch.binding.upsert` / `batch.binding.remove` — เปลี่ยนอุปกรณ์หรือ station
  ที่ผูกไว้

Event ต้อง idempotent ด้วย `eventId` และ Edge จะ apply เฉพาะ record ที่มี
revision ใหม่กว่าใน cache เท่านั้น ต้องมี acknowledgement ของสถานะ sync เพื่อให้
Cloud แสดงการตั้งค่า Edge ที่ล้าสมัยได้

## กรณีลงข้อมูล Batch ล่าช้าและข้อมูลย้อนหลัง

หลังบันทึก Batch ล่าช้า การทำงานปกติคือ **ผูกความสัมพันธ์ย้อนหลังเท่านั้น**
ไม่ใช่การทำ inference ซ้ำ:

1. ผู้ปฏิบัติงานระบุวันเริ่มเลี้ยง/ลงไก่จริง
2. ผู้ปฏิบัติงานเลือก batch, device/station และช่วงเวลาที่มีผลย้อนหลัง
3. ระบบ preview WeightVision session ที่ยัง unassigned และเข้าเงื่อนไข
4. เมื่อยืนยัน จึงใส่ `batchId` และ provenance เช่น breed กับ `age_days`

การผูกข้อมูลย้อนหลังใช้ทรัพยากรต่ำและไม่ใช้ CPU/GPU สำหรับ inference

Historical reprocessing เป็นทางเลือกแยก และทำได้เฉพาะเมื่อยังเก็บ source media
อยู่ ต้องสร้าง inference revision ใหม่ ห้ามเขียนทับ prediction เดิม

### QoS ของการ reprocess

- แยก queue `historical-reprocess` ออกจาก `realtime-inference`
- Realtime ต้องมี capacity เฉพาะและ priority สูงกว่า
- จำกัดงานย้อนหลังด้วย concurrency ต่อ Edge และ CPU/GPU utilization
- หยุดงานย้อนหลังอัตโนมัติเมื่อ realtime backlog หรือ latency เกิน threshold
- ค่าเริ่มต้นต้องเป็นการสั่งงานเอง/นอกเวลาทำการ และยกเลิกได้

## API ที่ต้องเพิ่ม

### Cloud control plane

- `GET /api/v1/edge/batch-context?tenantId=&siteId=&sinceRevision=`
- `POST /api/v1/batches/:id/bindings`
- `POST /api/v1/batches/:id/associate-sessions` (โหมด preview และ confirm)
- `POST /api/v1/weighvision/sessions/reprocess` (asynchronous; optional)

### Edge

- `GET /api/v1/edge-config/batch-context/:tenantId/:deviceId/:stationId`
- การสร้าง session ภายใน resolve จาก cache; normal device path ไม่ต้องให้ caller
  ส่ง `batchId` เอง

## แผนส่งมอบงาน

### Core path — 6 tickets

1. **Batch event contract และ Cloud outbox** — เพิ่ม event schema,
   transactional outbox, revision และ test ใน Tenant Registry
2. **Cloud batch-context/control API** — เปิดเผยข้อมูล batch/device binding ที่
   มีผลจริงและการ resolve model policy ผ่าน BFF/control endpoint
3. **Edge batch-context cache และ sync** — schema, incremental polling,
   idempotency, acknowledgement, stale-cache health check และ metrics
4. **Automatic Edge session binding** — resolve batch จาก device/station,
   เพิ่ม unassigned/ambiguous behaviour และส่งต่อ provenance
5. **Inference context และ model selection** — ใช้ cache แบบ offline,
   คำนวณอายุ บันทึก provenance และบังคับ fallback semantics
6. **Dashboard และ end-to-end acceptance** — แสดง batch/breed/age/model ใน
   session, หน้าจอจัดการ binding, Docker Compose smoke test และ E2E tests

### ความสามารถเสริม — เพิ่ม 1 ticket

7. **Historical association และ throttled reprocessing** — preview/confirm
   การผูกข้อมูล, queue แยก, quota, cancellation, audit trail และ inference
   revision

Core feature ใช้ 6 tickets; หากรวม re-predict ย้อนหลังแบบปลอดภัย ใช้ 7 tickets
แต่ละ ticket ต้องรัน unit/integration test ของตนเอง และ ticket สุดท้ายต้องรัน
`docker compose up -d --build` ใน environment ที่กำหนด พร้อม smoke test เส้นทาง
Edge → Cloud → Dashboard แบบครบถ้วน

## เกณฑ์การยอมรับงาน

1. Batch ที่ถูกสร้างและ bind ใน Cloud ต้องถึง target Edge cache ภายในช่วงเวลา
   sync ที่กำหนด
2. Capture จาก device ที่ bind ต้องสร้าง session ที่มี batch, breed, age และ
   model provenance ถูกต้อง
3. Cloud outage ต้องไม่ทำให้ inference หยุด หาก Edge cache ยังไม่หมดอายุ
4. หากไม่มี context ต้องได้ผล unassigned/fallback ที่มองเห็นได้; หาก context
   กำกวมต้องถูกปฏิเสธ
5. Dashboard ต้องแสดง batch และ weight provenance ตรงกับข้อมูลจาก read model
6. Historical association ต้องไม่ใช้ capacity ของ inference worker และ
   historical replay ต้องไม่ทำให้ realtime latency เกิน SLO ที่กำหนด
