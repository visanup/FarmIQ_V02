# BCES-001: Batch Event Contract และ Cloud Outbox

- **โครงการ:** Batch Context Sync for Edge WeightVision
- **สถานะ:** Verified complete — service/contract acceptance ผ่านบน clean-volume E2E
- **ลำดับ:** 1 / 7
- **ขนาดโดยประมาณ:** 2 วันทำงาน
- **ขึ้นต่อ:** ไม่มี

## เป้าหมาย

เมื่อ Dashboard สร้าง แก้ไข เปิดใช้งาน ปิดใช้งาน หรือเปลี่ยน binding ของ Batch
Tenant Registry ต้องบันทึก Batch และ event สำหรับ sync ไป Edge ใน transaction เดียวกัน
เพื่อไม่ให้ Cloud master data กับข้อมูลที่ Edge เห็นไม่สอดคล้องกัน

## ขอบเขต

- เพิ่ม event contract: `batch.upsert`, `batch.activate`, `batch.deactivate`,
  `batch.binding.upsert`, `batch.binding.remove`
- เพิ่ม revision ต่อ Batch และ transactional outbox ใน `cloud-tenant-registry`
- เพิ่ม schema/migration ของ outbox และ device/station binding
- เพิ่ม dispatcher ที่ส่ง event ไป Cloud control-plane pipeline แบบ idempotent

## นอกขอบเขต

- Edge cache และการสร้าง session อัตโนมัติ (BCES-003, BCES-004)
- การ reprocess inference ย้อนหลัง (BCES-007)

## Requirements

- ทุก event ต้องมี `eventId`, `eventType`, `revision`, `occurredAt`, tenant/farm/barn/batch
- `revision` เพิ่มขึ้นทุกครั้งที่ master data หรือ binding เปลี่ยน
- event ต้องถูกสร้างพร้อม Batch write; ถ้า transaction ไม่สำเร็จต้องไม่มี event
- retry ของ dispatcher ต้องไม่สร้างผลซ้ำ
- ต้องเก็บ audit: event, revision, สถานะส่ง และ error ล่าสุด

## การเปลี่ยนแปลงเชิงเทคนิค

| พื้นที่ | งาน |
|---|---|
| `cloud-tenant-registry` | Prisma migration: batch revision, binding และ outbox |
| `cloud-tenant-registry` | batch service เขียน Batch + outbox ใน transaction |
| shared contracts | TypeScript event type/payload และ validation schema |
| API | endpoint binding ตามสัญญาจาก BCES-002 |

ตัวอย่าง payload:

```json
{
  "eventId": "uuid",
  "eventType": "batch.upsert",
  "revision": 1,
  "tenantId": "t-001",
  "farmId": "f-001",
  "barnId": "b-001",
  "batchId": "uuid",
  "status": "active",
  "breedCode": "Arbor Acres Plus",
  "sex": "male",
  "startDate": "2026-09-08",
  "deviceBindings": [{ "deviceId": "wv-001", "stationId": "st-01" }]
}
```

## Acceptance Criteria

- [x] POST/PATCH Batch สำเร็จแล้วมี outbox event และ revision ถูกต้องใน transaction เดียวกัน
- [x] retry event เดิมไม่สร้าง Batch/binding ซ้ำ
- [x] event เก่ากว่า revision ล่าสุดไม่ทำให้ snapshot ถอยหลัง
- [x] deactivate binding แล้วไม่มี active binding ถูกเผยแพร่
- [x] audit query ระบุ event ที่ส่งไม่สำเร็จและสั่ง retry ได้

## การทดสอบ

- Unit: revision, payload validation, idempotency
- Integration: PostgreSQL transaction rollback และ outbox dispatcher retry
- Contract: validate JSON ของ event กับ shared schema

### หลักฐานการยืนยัน (2026-09-25)

- Jest Tenant Registry ผ่าน **3 suites / 11 tests**: `batchService`,
  `batchContextService`, `batchContextOutboxService`; ครอบคลุม revision,
  snapshot/delta, cross-scope binding, dispatcher success/failure retry และ
  removal event
- Clean-volume E2E สร้าง Batch `8551fbbb-a537-43ab-a4d0-604f53fde329` ผ่าน BFF
  ได้ revision `1` และ bind device E2E ได้ revision `2`; เป็นการเขียนผ่าน
  transaction/outbox path จริงใน database `bces-e2e-cloud-postgres`
- ใช้เฉพาะ Compose project/volumes `bces-e2e-*`; ไม่มีการเขียน volume dev หรือ
  Production

## Deployment / Rollback

- ใช้ additive migration ก่อน deploy code ที่อ่าน revision/outbox
- feature flag `BATCH_CONTEXT_OUTBOX_ENABLED=false` เป็นค่าเริ่มต้นใน rollout
- rollback โดยปิด flag; ห้ามลบ event หรือ revision ที่เขียนแล้ว

## ความเสี่ยง

| ความเสี่ยง | การลดความเสี่ยง |
|---|---|
| event ซ้ำหรือไม่เรียงลำดับ | idempotent `eventId` และ monotonic revision |
| Batch เดิมไม่มี binding | เผยแพร่เป็น unbound; Edge ต้องไม่เดา |
