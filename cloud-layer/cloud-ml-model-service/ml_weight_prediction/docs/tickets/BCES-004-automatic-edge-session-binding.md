# BCES-004: Automatic Edge Session Binding

- **โครงการ:** Batch Context Sync for Edge WeightVision
- **สถานะ:** Done (2026-09-24)
- **ลำดับ:** 4 / 7
- **ขนาดโดยประมาณ:** 2 วันทำงาน
- **ขึ้นต่อ:** BCES-003

## เป้าหมาย

ให้ `edge-weighvision-session` เลือก Batch ที่ถูกต้องจาก local cache เมื่อ device/station
เริ่ม session และ stamp บริบทนั้นลง session อย่าง immutable

## ขอบเขต

- เพิ่ม Batch context resolver ใน path สร้าง session
- บันทึก batch ID, context revision และ resolution status ลง WeightVision session
- เพิ่มสถานะ `unassigned` และ error `BATCH_CONTEXT_AMBIGUOUS`
- ส่ง Batch provenance ใน `weighvision.session.created` และ finalization event

## กฎธุรกิจ

1. หากพบ active binding เดียวที่ตรง tenant/farm/barn/device/station ให้ bind อัตโนมัติ
2. หากไม่พบ ให้สร้าง unassigned session และระบุ fallback reason
3. หากพบมากกว่าหนึ่ง ให้ปฏิเสธก่อนรับ media/inference; ห้ามเลือกเอง
4. caller ปกติจาก IoT ไม่ควรส่ง `batchId`; field นี้สงวนไว้สำหรับ controlled admin/test
   override ที่ audit ได้

## การเปลี่ยนแปลงเชิงเทคนิค

| พื้นที่ | งาน |
|---|---|
| `edge-weighvision-session` | schema migration และ resolver client |
| Edge session event | เพิ่ม batch context revision/resolution/provenance |
| API validation | แยก internal override จาก normal device path |
| observability | metric ของ resolved/unassigned/ambiguous |

## Acceptance Criteria

- [x] session จาก `wv-001/st-01` ได้ Batch ที่ active โดยไม่ส่ง `batchId` จาก caller
- [x] session เก็บ Batch/context revision แม้ binding เปลี่ยนภายหลัง
- [x] ไม่มี binding ได้ unassigned + fallback reason ที่ Dashboard แสดงได้
- [x] binding กำกวมได้ error code ที่ชัดเจนและไม่สร้าง session ครึ่งเดียว
- [x] Cloud event ที่ส่งออกมี Batch provenance ตรงกับ session ใน Edge

## การทดสอบ

- Unit: resolver ทุก outcome และ authorization ของ override
- Integration: session DB + cache lookup + sync outbox event
- E2E: device capture → session event พร้อม Batch โดยไม่ส่ง Batch จาก test client

### ผลการยืนยัน

- Prisma migration แบบ additive เพิ่ม context revision/resolution/reason/provenance
- Unit tests ครอบคลุม resolver outcomes และ authorization ของ override
- Integration ใช้ PostgreSQL และ `sync_outbox` จริง; resolver ให้ cached context
  ของ `wv-001/st-01` โดยไม่ส่ง `batchId` แล้วตรวจ created/finalized event
  มี provenance ตรงกับ immutable session
- TypeScript build ผ่าน และ Jest ทั้ง service ผ่าน 22/22
- ลบข้อมูล integration test หลังจบ (`weight_sessions|sync_outbox = 0|0`)

## Deployment / Rollback

- deploy schema ก่อน resolver
- เปิด feature flag ทีละ site/station และ monitor unassigned rate
- rollback ปิด auto-bind; session ที่ stamp แล้วต้องคง immutable

## Revalidation 2026-09-28

Edge session build ผ่านและ targeted Jest 4 suites / 12 tests. E2E session
`bces-validate-3fb6f3591092` ส่งเฉพาะ tenant/farm/barn/device/station แต่ได้ Batch,
revision และ immutable provenance ถูกต้อง; caller ไม่ส่ง `batchId`.
