# BCES-001 ถึง BCES-007 Validation Report

วันที่ตรวจ: 2026-09-28  
ขอบเขต: source, migration, targeted acceptance tests, build/type-check,
clean-volume realtime E2E, historical reprocess lineage และ Dashboard runtime

## สรุปผล

ฟังก์ชันหลักของ BCES-001 ถึง BCES-007 เชื่อมกันครบใน isolated stack
`bces-e2e-*` ตั้งแต่ Batch context ใน Cloud, Edge policy cache, immutable session
context, inference, transactional outbox, sync-forwarder, Cloud read-model, BFF
จนถึง Dashboard. รอบ realtime ล่าสุดใช้ session
`bces-validate-3fb6f3591092` และสร้าง inference เพียงหนึ่งรายการ
`604006e1-40f5-4367-9f36-48650c5f644b` หลังแก้ mock ไม่ให้ enqueue ซ้ำ.

สถานะ feature acceptance: **ผ่าน**. สถานะ full repository validation:
**ผ่านแบบมีข้อยกเว้นที่บันทึกไว้** เพราะ Dashboard full type-check/test suite ยังมี
baseline errors นอก BCES และ runtime inference image ไม่มี `pytest`; รายละเอียดอยู่
ในหัวข้อข้อจำกัด. Production build และ runtime E2E ของเส้นทาง BCES ผ่าน.

## Validation matrix

| Ticket | หลักฐาน implementation | หลักฐาน test/runtime | ผล |
|---|---|---|---|
| BCES-001 | Batch event contract, Tenant Registry transaction/outbox, Prisma additive migrations | Tenant Registry targeted Jest 3 suites / 11 tests; create/update revision, idempotency และ outbox assertions ผ่าน | ผ่าน |
| BCES-002 | Tenant Registry snapshot/delta/ETag, binding validation; BFF Edge credential/scope proxy และ model-policy resolver | BFF targeted 3 suites / 11 tests; full BFF 13 suites / 47 tests; live snapshot มี 2 contexts, revision 3, ETag และ fallback policy | ผ่าน |
| BCES-003 | `edge-policy-sync` cache/sync state, revision guard, internal lookup และ metrics | TypeScript `--noEmit` ผ่าน; container unit 9/9 และ DB integration 1/1; live lookup resolve `t-001/wv-001/st-001` เป็น `batch-e2e-t001` revision 1 | ผ่าน |
| BCES-004 | Session create route รับ physical scope เท่านั้น; resolver stamp immutable context และ session outbox | Edge session 4 suites / 12 tests; live create ไม่ส่ง `batchId` แต่ได้ Batch, station, provenance และ revision ถูกต้อง | ผ่าน |
| BCES-005 | Inference ใช้ local/session context, age/model fallback provenance; media-store completion handshake | รอบล่าสุดได้ weight 5.16, breed ROSS-308, age 24, `shadow_stub`, `NO_SITE_SUBSCRIPTION`; count ของผลต่อ media/session เท่ากับ 1 | ผ่าน |
| BCES-006 | Multi-source sync-forwarder, Cloud ingestion/read-model/BFF และ Dashboard fields | sync-forwarder current integration 7/7 กับ disposable `TEST_DATABASE_URL`; source build ผ่าน; Cloud BFF พบ session ล่าสุด 1 รายการ; Dashboard production build ผ่านและ browser แสดง Station/Batch/Breed/Age/Weight/Mode/Fallback | ผ่าน |
| BCES-007 | association audit/job/revision migrations, separated historical queue, preflight, pause/resume/cancel และ immutable revision lineage | read-model safety 5/5; persisted E2E ยืนยัน revision `03c3a9e4-...` อ้าง original `e15d3256-...`, ทั้ง original/revision ยังอยู่; backlog pause/cancel/resume evidence ผ่าน | ผ่าน |

## Build และ test ที่ยืนยัน

- `@farmiq/contracts`: `tsc -p tsconfig.json --noEmit` ผ่าน (host build เขียน
  `dist` ไม่ได้จาก file lock จึงใช้ no-emit validation).
- `cloud-tenant-registry`: Prisma generate และ TypeScript build ผ่านใน container.
- `cloud-api-gateway-bff`: Prisma generate/build ผ่าน; full Jest 13 suites / 47
  tests ผ่าน.
- `cloud-weighvision-readmodel`: Prisma generate/build ผ่าน; historical safety
  tests 5/5 ผ่าน.
- `edge-policy-sync`: type-check ผ่าน; unit 9/9 และ DB integration 1/1 ผ่าน.
- `edge-weighvision-session`: build ผ่าน; 4 suites / 12 tests ผ่าน.
- `edge-sync-forwarder`: Prisma generate/build ผ่าน. Current integration test 7/7
  ใช้ฐาน disposable `edge_sync_forwarder_test`; operational `farmiq` ยังมี 12
  tables หลัง test. Unit assertions ที่ไม่แตะ DB ผ่าน 39 tests.
- `dashboard-web`: `vite build` ผ่าน (15,318 modules, 1m49s). Browser runtime
  ที่ `http://127.0.0.1:5542` login และ render BCES fields ผ่าน.
- Compose merge validation ของ Cloud และ Edge override: `config --quiet` ผ่าน.
- ทุก container ที่จำเป็นใน `bces-e2e-*` healthy ตอนจบการตรวจ.

## Realtime E2E ล่าสุด

1. POST session ด้วย `tenant=t-001`, `farm=f-001`, `barn=b-001`,
   `device=wv-001`, `station=st-001`; caller ไม่ส่ง `batchId`.
2. Edge resolve `batch-e2e-t001`, revision 1, breed ROSS-308, sex mixed.
3. mock IoT upload image ไป MinIO และ complete ผ่าน media-store. เมื่อ media-store
   ส่ง `inference_job_id` กลับมา mock จะไม่ POST job ซ้ำ.
4. Edge inference ตอบ `count=1`, weight 5.16 kg, confidence 0.58, age 24,
   `prediction_mode=shadow_stub`, fallback `NO_SITE_SUBSCRIPTION`.
5. sync-forwarder ส่ง event ถึง Cloud; BFF list พบ session เดียวกันพร้อม inference.
6. Dashboard list และ detail แสดง Station, Batch, ROSS-308/day 24, 5.16 kg,
   SHADOW_STUB และ NO_SITE_SUBSCRIPTION. Unassigned rows แสดงคำแนะนำให้ bind.

## Historical reprocess E2E

หลักฐาน read-only จาก `bces-e2e-cloud-postgres` สำหรับ `hist-e2e-001`:

```text
inferenceId:         03c3a9e4-bd1b-4e20-8ba2-dec47d47c962
originalInferenceId: e15d3256-dc7e-47b3-ad0b-05c47025454a
historicalJobId:     3e2dd851-0f80-47ff-91e8-dfe6a3f4ba6d
revision:            1
original exists:     true
revision exists:     true
association audits:  1
```

ผล controlled backlog ที่บันทึกไว้ยืนยันว่า historical job pause ระหว่าง realtime,
cancel ได้ก่อนเริ่ม, resume จน completed และไม่ overwrite original.

## Defects ที่แก้ระหว่าง validation

1. `vision-input-mock` เคย enqueue inference ซ้ำหลัง media-store auto-trigger.
   แก้ให้ reuse `inference_job_id` และใช้ authoritative `media_id`; E2E รอบใหม่
   เหลือ result เดียว.
2. Dashboard sessions list ใช้ `initialData: []` ทำให้ React StrictMode ค้างที่
   empty state แม้ BFF ตอบ 20 records. เอา seed นี้ออก; rebuild แล้ว browser render
   ตารางและ BCES columns สำเร็จ.
3. E2E Edge credential ถูก hard-code และหมดอายุ. Override เปลี่ยนเป็น required
   environment variable `BCES_EDGE_CLOUD_TOKEN` เพื่อบังคับ short-lived token.
4. Dashboard clean container mount Vite artifact ที่ validate แล้วแบบ read-only
   จึงไม่ต้อง rebuild/mutate dev image.

## ข้อจำกัดและ baseline ที่ไม่ใช่ BCES blocker

- Dashboard full `tsc --noEmit` ยัง fail จาก baseline หลายส่วนของแอป เช่น package
  link `@farmiq/api-client`, unused/type mismatches นอก BCES. Production Vite build
  และ browser E2E ของ BCES ผ่าน.
- Dashboard targeted Vitest ถูก test harness หยุดก่อน assertion ด้วย
  `Cannot set property testPath ... which has only a getter`; ไม่ใช่ BCES assertion
  failure. Browser runtime validation ใช้แทนในรอบนี้.
- Runtime image ของ Python inference ไม่มี `pytest` และ host environment ไม่มี
  pytest จึงไม่ได้ rerun Python suite ในรอบนี้. Ticket มีผลเดิม 9 tests; current
  container health และ realtime/historical E2E ผ่าน.
- การ rebuild mock image ถูก Docker Hub metadata timeout; validation จึงใช้ cached
  image พร้อม bind-mount source read-only. พฤติกรรมที่แก้ถูกพิสูจน์ด้วย result count 1.
- Notification service, Cloud config-rules และ production ML subscription service
  ไม่อยู่ใน minimum BCES stack. Notification API จึงตอบ 502 ใน console แต่ไม่ทำให้
  WeighVision query หรือ Dashboard rendering ล้มเหลว.

## Safety evidence

- ใช้เฉพาะ containers/network/volumes ที่ขึ้นต้น `bces-e2e-*`.
- ไม่ stop, rebuild, remove หรือ migrate dev/production resources.
- sync-forwarder destructive integration ใช้เฉพาะ explicit
  `TEST_DATABASE_URL=.../edge_sync_forwarder_test`; ไม่มี fallback ไป operational
  `DATABASE_URL`.
- ไม่ใช้ `prisma migrate reset` หรือ `synchronize(true)` กับฐาน `farmiq` ที่แชร์.

ขั้นตอนทำซ้ำ, validation queries, troubleshooting และ rollback อยู่ใน
`runbook/compose/BCES-CLEAN-VOLUME-E2E.md`.
