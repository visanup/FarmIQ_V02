# BCES-003: Edge Batch Context Cache และ Sync

- **โครงการ:** Batch Context Sync for Edge WeightVision
- **สถานะ:** Done (2026-09-24)
- **ลำดับ:** 3 / 7
- **ขนาดโดยประมาณ:** 2 วันทำงาน
- **ขึ้นต่อ:** BCES-002

## เป้าหมาย

ขยาย `edge-policy-sync` ให้ดึงและเก็บ Batch context แบบ local cache ที่ versioned
เพื่อให้ Edge resolve Batch และ model policy ได้แม้ Cloud unavailable ชั่วคราว

## ขอบเขต

- เพิ่ม `edge_batch_context_cache` และ sync state
- incremental poll, ETag/revision, idempotent upsert และ stale-cache detection
- expose internal lookup endpoint สำหรับ Edge session/inference
- metrics และ readiness ที่สะท้อน cache age/sync failure

## Data Model

| กลุ่มข้อมูล | ตัวอย่าง |
|---|---|
| Scope | tenant, farm, barn, device, station, batch |
| ML context | species, breed, sex, start date, package, version |
| Sync metadata | revision, source event ID, fetchedAt, expiresAt, hash |
| Lifecycle | active, deactivated, superseded |

ต้องมี unique key ที่ป้องกัน active binding ซ้ำใน scope เดียวกัน หรืออย่างน้อยต้อง
ตรวจความกำกวมให้ session resolver เห็นได้ชัดเจน

## API ภายใน Edge

```text
GET /api/v1/edge-config/batch-context/:tenantId/:deviceId/:stationId
```

ผลลัพธ์ต้องบอก `resolved`, `unassigned`, `ambiguous` หรือ `stale` อย่างชัดเจน

## Acceptance Criteria

- [x] Edge รับ full snapshot และ delta แล้ว upsert ตาม revision ได้
- [x] event/revision เก่าไม่เขียนทับ context ใหม่
- [x] Cloud outage ไม่หยุด lookup หาก cache ยังไม่หมดอายุ
- [x] stale หรือ ambiguous context มีเหตุผลที่ machine-readable
- [x] metrics มี sync success/failure, lag, cache age และ context resolution outcome

## การทดสอบ

- Unit: revision ordering, duplicate event, expiry และ ambiguity
- Integration: policy-sync กับ PostgreSQL test DB และ mock BFF
- Resilience: timeout/retry/backoff และ restart แล้ว cache คงอยู่

### ผลการยืนยัน

- TypeScript type-check และ Docker build ผ่าน
- Unit/resilience tests ผ่าน 9 รายการ
- Integration test กับ Edge PostgreSQL และ mock BFF ผ่าน 1 รายการ
- ทดสอบ snapshot, delta/ETag 304, duplicate, revision เก่า, TTL/stale,
  ambiguity, timeout/backoff และสร้าง service instance ใหม่โดย cache ยังอยู่
- หลัง integration test ลบข้อมูล tenant ทดสอบแล้ว (`0|0|0`)

## Deployment / Rollback

- additive schema migration และ run cache sync shadow mode ก่อนใช้จริง
- feature flag `BATCH_CONTEXT_CACHE_ENABLED`
- rollback โดยปิด flag และให้ session ใช้ current optional caller-supplied Batch behaviour

## ความเสี่ยง

| ความเสี่ยง | การลดความเสี่ยง |
|---|---|
| cache ล้าสมัยหลังเปลี่ยน flock | revision, short TTL, stale alert และ deactivate event |
| Batch เดียวผูกหลาย station | ทำ binding เป็น record อิสระ ไม่แชร์ mutable state |

## Revalidation 2026-09-28

Type-check ผ่าน, container unit 9/9 และ DB integration 1/1. Live lookup ของ
`t-001/wv-001/st-001` resolve เป็น `batch-e2e-t001` revision 1 พร้อม model policy;
sync failures เป็นศูนย์หลัง Cloud พร้อม.
