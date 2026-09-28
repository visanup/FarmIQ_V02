# BCES-005: Inference Batch Context และ Model Selection

- **โครงการ:** Batch Context Sync for Edge WeightVision
- **สถานะ:** Verified complete — clean-volume E2E และ local performance measurement ผ่านแล้ว
- **ลำดับ:** 5 / 7
- **ขนาดโดยประมาณ:** 2 วันทำงาน
- **ขึ้นต่อ:** BCES-003, BCES-004

## เป้าหมาย

ให้ `edge-vision-inference` ใช้ Batch context จาก local Edge cache เพื่อคำนวณอายุ
และเลือก model package โดยไม่ต้องเรียก Cloud ใน realtime path

## ขอบเขต

- อ่าน immutable batch context จาก session/cache
- คำนวณ `age_days` จาก local capture date และ `startDate`
- resolve package/version จาก cached model policy
- บันทึก complete inference provenance ลง result และ sync event
- กำหนด fallback semantics ที่ชัดเจนสำหรับ unassigned/stale/no-subscription

## Requirements

- ไม่ทำ network call ไป Cloud ใน hot path ของ realtime inference
- `age_days` ใช้ farm timezone และต้องไม่เป็นค่าติดลบ
- ผลลัพธ์ต้องมี `batchId`, `breedCode`, `sex`, `ageDays`, model package/version,
  prediction mode และ fallback reason เมื่อเกี่ยวข้อง
- หาก model package ไม่พร้อม ต้องใช้ fallback ที่กำหนดหรือ fail ตาม policy;
  ห้ามอ้างว่าใช้ breed-specific model ทั้งที่ไม่ได้ใช้

## Acceptance Criteria

- [x] inference ของ Batch Arbor Acres Plus บันทึก breed/age/model provenance ครบ
- [x] ตัด Cloud network ใน hot path; unit test ยืนยันว่าไม่เรียก subscription refresh
- [x] Batch start date หลัง capture ทำให้ได้ validation/fallback outcome ที่ตรวจสอบได้
- [x] ไม่มี subscription แสดง `fallback` อย่างตรงไปตรงมา ไม่ใช่ package ปลอม
- [x] Cloud read model และ Dashboard รองรับ provenance แบบ additive

## การทดสอบ

- pytest unit: age calculation, timezone, model policy, fallback
- Integration: session context → inference result → Edge sync payload
- Performance: realtime latency ไม่เกิน baseline ที่ตกลงหลังเปิด context lookup

## ผลการตรวจ implementation

- pytest: `tests/test_job_service.py -q` ผ่าน 9 tests หลังเพิ่ม fallback ของ
  session start time และ station provenance
- Runtime E2E: inference result `17a24acf-cd43-4d67-8d45-a4472174d4d7` มี batch,
  `Arbor Acres Plus`, `age_days: 16`, station ที่ bind จริง และ
  `fallback_reason: NO_SITE_SUBSCRIPTION`; Edge sync forwarder ส่งถึง Cloud
  read-model สำเร็จ
- ไม่มี Cloud call ใน inference hot path สำหรับ context ที่ stamp ไว้ใน session;
  lookup ใช้ immutable session/cache context
- clean-volume E2E เมื่อ 2026-09-25 ใช้ resources `bces-e2e-*` เท่านั้น:
  mock capture → session context `t-001/f-001/b-001/wv-001/st-001` → inference
  `5.16 kg` → outbox ACK → Cloud read-model/BFF สำเร็จ โดยมี `batch-e2e-t001`,
  breed `broiler`, sex `mixed`, age `21`, `shadow_stub` และ
  `NO_SITE_SUBSCRIPTION` ครบใน provenance
- วัด local clean-volume baseline จาก mock capture จำนวน 5 รอบ: min `280 ms`,
  max `342 ms`, p95 `342 ms`. ตัวเลขนี้เป็น baseline ของ development E2E
  (`shadow_stub`) ไม่ใช่ SLO ของ Production หรือ breed-specific model

## Deployment / Rollback

- feature flag `BATCH_CONTEXT_INFERENCE_ENABLED`
- publish result schema additive ก่อน Dashboard อ่าน field ใหม่
- rollback ปิด flag และยังเก็บ provenance ของผลที่สร้างแล้ว
- การทดสอบ clean-volume ไม่ deploy หรือเชื่อมต่อ Production; ห้ามนำ E2E JWT หรือ
  Compose override ไปใช้กับ Production

## ความเสี่ยง

| ความเสี่ยง | การลดความเสี่ยง |
|---|---|
| model bundle/cache ไม่พร้อม | explicit fallback + package readiness metric |
| เวลา capture ต่าง timezone | บังคับ farm timezone และ test boundary ของวัน |
