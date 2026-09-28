# BCES-002: Cloud Batch Context และ Control API

- **โครงการ:** Batch Context Sync for Edge WeightVision
- **สถานะ:** Verified complete — control API acceptance ผ่านบน clean-volume E2E
- **ลำดับ:** 2 / 7
- **ขนาดโดยประมาณ:** 1.5 วันทำงาน
- **ขึ้นต่อ:** BCES-001 สำหรับข้อมูล revision/outbox

## เป้าหมาย

ให้ Edge ดึง snapshot ที่ authoritative ของ Batch context และ device/station binding
ผ่าน Cloud BFF/control-plane โดยใช้ incremental revision และ tenant-scoped authorization

## ขอบเขต

- เพิ่ม endpoint สำหรับ delta/snapshot batch context ของ edge site
- เพิ่ม API สำหรับจัดการ Batch binding โดยผู้มีสิทธิ์
- resolve model policy จาก species/breed/sex/site ก่อนส่งให้ Edge
- รองรับ ETag หรือ revision cursor สำหรับลด bandwidth

## API ที่เสนอ

```text
GET  /api/v1/edge/batch-context?tenantId=&siteId=&sinceRevision=
POST /api/v1/batches/:id/bindings
DELETE /api/v1/batches/:id/bindings/:bindingId
```

`GET` ส่งเฉพาะ context ที่ใหม่กว่า `sinceRevision`; หาก cursor ใช้ไม่ได้ให้ส่ง
full snapshot พร้อม `nextRevision` และ ETag

## กฎด้านความปลอดภัย

- Edge ใช้ service credential ที่จำกัด tenant/site
- ห้ามรับ `tenantId` จาก body โดยไม่มีการตรวจ claim/header ที่เชื่อถือได้
- ตรวจทุก binding ว่า device/station อยู่ใน farm/barn ของ Batch เดียวกัน
- log request ID, trace ID, tenant, site และ revision โดยไม่ log token

## การเปลี่ยนแปลงเชิงเทคนิค

| พื้นที่ | งาน |
|---|---|
| Cloud BFF | control routes, authz และ aggregation client |
| Tenant Registry | query effective batch/binding snapshot |
| ML model service | resolver model policy/package ที่ active |
| OpenAPI/contracts | request/response schema และ error envelope |

## Acceptance Criteria

- [x] Edge credential เห็นเฉพาะ context ของ tenant/site ตนเอง
- [x] snapshot ระบุ Batch, breed, sex, startDate, binding, revision และ model policy
- [x] delta request ที่ไม่มีการเปลี่ยนแปลงตอบ empty delta/304 โดยไม่ส่ง payload เต็ม
- [x] binding ที่ cross-tenant หรือ cross-barn ถูกปฏิเสธด้วย validation error
- [x] BFF ส่ง error envelope ตามมาตรฐาน FarmIQ

## การทดสอบ

- Unit: policy resolution, tenant/site authorization, revision filtering
- Integration: BFF → Tenant Registry → model policy resolver
- Contract: OpenAPI และ edge client compatibility test

### หลักฐานการยืนยัน (2026-09-25)

- Jest BFF ผ่าน **1 suite / 6 tests** (`edgeBatchContextController.spec.ts`):
  tenant/site authorization, cursor, ETag/304, fallback policy และ standard
  downstream error envelope
- Edge service credential ที่ tenant `t-001`, site `site-e2e` ได้ snapshot
  revision `1`, ETag
  `"edge-batch-context-t-001-site-e2e-1-fallback"` พร้อม Batch/breed/sex/
  startDate/device/station/model fallback policy; site อื่นตอบ `403`
- conditional request ที่ revision เดิมตอบ `304`; Tenant Registry unit test
  ยืนยันว่า cross-barn binding ถูกปฏิเสธ และ BFF integration ใช้ fallback
  `NO_SITE_SUBSCRIPTION` อย่าง explicit

## Deployment / Rollback

- deploy endpoint แบบ read-only ก่อนเปิด Edge polling
- backward compatible: context ที่ไม่มี `modelPolicy` ต้องสื่อว่า fallback เท่านั้น
- rollback โดยปิด route จาก Edge config; data ใน Cloud ไม่ถูกแก้ไข

## ความเสี่ยง

| ความเสี่ยง | การลดความเสี่ยง |
|---|---|
| model package ไม่ตรง breed | resolver ต้องตอบ explicit fallback reason |
| Edge poll ถี่เกิน | ETag/revision และ rate limit ต่อ site |
