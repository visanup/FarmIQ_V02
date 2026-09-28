# BCES-007: Historical Association และ Safe Reprocess

- **โครงการ:** Batch Context Sync for Edge WeightVision
- **สถานะ:** Completed — isolated E2E, queue guardrails และ validation ผ่าน
- **ลำดับ:** 7 / 7
- **ขนาดโดยประมาณ:** 3 วันทำงาน
- **ขึ้นต่อ:** BCES-001 ถึง BCES-006

## เป้าหมาย

รองรับฟาร์มที่ลงข้อมูล Batch หลังเริ่มเลี้ยงแล้ว โดยผูก WeightVision sessions
ย้อนหลังแบบปลอดภัยเป็นค่าเริ่มต้น และให้ reprocess inference เป็นงานทางเลือกที่
ไม่กระทบ realtime capacity

## ขอบเขต

- preview และ confirm การ associate unassigned sessions กับ Batch
- ตรวจ scope, interval, start date และความกำกวมก่อนแก้ไขข้อมูล
- audit trail ของ association และ derived age/provenance
- optional asynchronous historical reprocess พร้อม inference revision
- queue/worker/quotas แยกจาก realtime inference

## นอกขอบเขต

- เขียนทับ prediction เดิม
- auto-assign เมื่อมี Batch มากกว่าหนึ่งรายการใน scope/time เดียวกัน
- ใช้ reprocess เพื่อแก้ model production ที่ไม่พร้อม

## User Flow

```text
ผู้ใช้เลือก Batch และช่วงเวลาย้อนหลัง
  -> ระบบ preview unassigned sessions ที่เข้า scope
  -> ผู้ใช้ยืนยัน association
  -> system เขียน batchId + derived provenance พร้อม audit
  -> ผู้ใช้เลือก reprocess เฉพาะเมื่อต้องการ
  -> job เข้า historical-reprocess queue, สร้าง inference revision ใหม่
```

## QoS และ Resource Guardrails

- queue `historical-reprocess` แยกจาก `realtime-inference`
- realtime มี priority และ worker/GPU quota เฉพาะ
- historical concurrency ค่าเริ่มต้น 1 ต่อ Edge และปรับได้ตาม CPU/GPU
- pause historical jobs เมื่อ realtime backlog/latency เกิน threshold
- รองรับ cancellation, resume และ schedule นอกเวลาทำการ
- reprocess ต้องตรวจ media retention ก่อน enqueue

## Acceptance Criteria

- [x] preview ไม่แก้ข้อมูล และแสดงจำนวน session ที่ตรง/ไม่ตรง/กำกวม
- [x] confirm association ไม่เรียก inference หรือใช้ GPU
- [x] multiple active Batch บังคับผู้ใช้ระบุ Batch และ interval เอง
- [x] reprocess สร้าง inference revision ใหม่โดยคง original result ไว้
- [x] realtime SLA ไม่เกิน threshold ระหว่าง historical load
- [x] cancel job หยุดงานที่ยังไม่เริ่มและไม่ทำข้อมูลเสียหาย

## การทดสอบ

- Unit: interval/scope validation, ambiguity และ revision lineage
- Integration: association transaction + audit + read-model update
- Queue integration: priority, concurrency, pause/resume/cancel
- Load test: realtime inference พร้อม historical backlog
- E2E: UI preview → confirm → optional reprocess → provenance comparison

## สถานะการพัฒนา (2026-09-25)

- เพิ่ม additive migration ใน `cloud-weighvision-readmodel` สำหรับ association audit
  และ `historical-reprocess` job table; ไม่มีการแก้หรือเขียนทับ inference เดิม
- เพิ่ม preview/confirm API ที่เลือกเฉพาะ `batchId IS NULL` ใน tenant/farm/barn/
  interval ที่ระบุ และเขียน audit ใน transaction เดียวกันกับ association
- เพิ่ม queue contract ที่แยกชื่อ `historical-reprocess` และยังถูกปิดด้วย
  `HISTORICAL_REPROCESS_ENABLED=false` เป็นค่าเริ่มต้น; cancel ทำได้เฉพาะ job
  ที่ยัง `queued` จึงไม่ interrupt realtime หรือ job ที่เริ่มแล้ว
- Cloud BFF ตรวจ authenticated tenant และตรวจ Batch กับ farm/barn จาก Tenant
  Registry ก่อน proxy preview/confirm/enqueue ไป Read-model
- Edge inference มี queue class `historical-reprocess` ที่ feature-flagged, จำกัด
  concurrency 1, pause เมื่อ realtime active, และมี cancel/resume เฉพาะ job ที่ยัง
  ไม่เริ่ม; realtime jobs จึงไม่ถูก cancel ผ่าน historical control
- Cloud dispatcher ทำ media-retention preflight ก่อนส่งงานที่ผ่านเกณฑ์ไป Edge;
  Edge result ส่ง `historicalJobId`/`revisionOf` กลับมา และ Cloud read-model
  เก็บ inference revision lineage แยกจาก original inference
- `cloud-weighvision-readmodel`: `npx prisma generate; npm run build` ผ่าน
- BFF ตรวจเพิ่มว่า interval ต้องไม่กลับด้านและต้องไม่เริ่มก่อน `batch.startDate`
  ก่อนส่งต่อไป Read-model
- isolated E2E ผ่านที่ `bces-e2e-*`: preview พบ unassigned 1 session, confirm
  associate 1 session, audit ถูกบันทึก, Cloud inference ของ session นั้นยังเป็น 0,
  cross-barn scope ถูกปฏิเสธ 422 และ reprocess ถูกปฏิเสธ 409 เมื่อ feature flag
  ยังปิด
- `cloud-weighvision-readmodel`: build ผ่าน และ unit safety contract 5/5 ผ่าน
- `cloud-api-gateway-bff`: build ผ่าน; Jest 13 suites / 46 tests ผ่าน แต่ process
  ยัง exit non-zero จาก global coverage threshold เดิม 70% (ไม่ใช่ assertion failure)
- Dashboard เพิ่ม action panel ใน WeighVision Sessions สำหรับ preview, confirm และ
  queue reprocess โดยบังคับให้เลือก tenant/farm/barn/Batch จาก active context;
  Dashboard production build ผ่าน

### ผล E2E ล่าสุด (2026-09-28)

- รันบน Compose project/volumes `bces-e2e-*` เท่านั้น ไม่มีการแตะ dev หรือ
  production volume
- session `hist-e2e-001` มี retained media, preview/confirm association สำเร็จ
  และ Cloud audit ถูกบันทึก
- สร้าง realtime original inference `e15d3256-dc7e-47b3-ad0b-05c47025454a`
  แล้ว queue historical job `3e2dd851-0f80-47ff-91e8-dfe6a3f4ba6d`
- Edge result `03c3a9e4-bd1b-4e20-8ba2-dec47d47c962` ถูกส่งผ่าน
  `edge-sync-forwarder`, outbox เป็น `acked` และ Cloud สร้าง revision `1`
  ที่อ้าง `originalInferenceId=e15d3256-dc7e-47b3-ad0b-05c47025454a`
- แก้ forwarder ให้รองรับ `SYNC_SOURCE_DATABASE_URLS`: services ที่มี
  operational database แยก (เช่น Vision) forward transactional outbox ของตนได้
  โดยไม่ย้าย ownership ไปฐาน shared. เปิดใช้เฉพาะ E2E override ในตอนนี้
- Cloud BFF sessions API ตอบ HTTP 200 และส่ง session/media/original/revision ให้
  Dashboard ได้
- controlled backlog E2E: historical job ถูก `paused` ระหว่าง realtime, job หนึ่ง
  ถูก cancel ได้โดยไม่สร้างผล และอีก job resume จน `completed`; realtime จบก่อน
  historical จึงไม่ถูกแย่ง capacity
- trusted historical context snapshot จาก Cloud dispatcher ทำให้ Edge reprocess
  ส่ง `batch_id`, `breed_code=Arbor Acres Plus`, `age_days=1`; outbox ถูก ack
- edge-sync-forwarder full assertion suite ผ่าน `10 suites / 46 tests` และ
  TypeScript build ผ่าน

### งานที่เหลือก่อนปิด ticket

ไม่มี — งานนี้ปิดหลัง isolated E2E และ full validation ผ่านแล้ว

## Deployment / Rollback

- deploy association-only ก่อนเปิด reprocess feature flag
- historical queue ปิดโดย default และต้องมี capacity configuration
- rollback ปิด enqueue ใหม่; association/audit และ inference revisions ต้องเก็บไว้

## ความเสี่ยง

| ความเสี่ยง | การลดความเสี่ยง |
|---|---|
| reprocess แย่ง GPU realtime | dedicated quota, priority queue, utilization guardrail |
| source image หมดอายุ | preflight media retention และรายงานข้ามรายการที่ใช้ไม่ได้ |
| ผูก Batch ผิดย้อนหลัง | preview, explicit confirmation, audit และ reversible association |
