# BCES-006: Dashboard, Observability และ End-to-End Acceptance

- **โครงการ:** Batch Context Sync for Edge WeightVision
- **สถานะ:** Verified complete — clean-volume critical path และ Dashboard runtime acceptance ผ่านแล้ว
- **ลำดับ:** 6 / 7
- **ขนาดโดยประมาณ:** 2.5 วันทำงาน
- **ขึ้นต่อ:** BCES-001 ถึง BCES-005

## เป้าหมาย

ทำให้ผู้ใช้ตรวจสอบได้จาก Dashboard ว่า WeightVision prediction เป็นของ Batch ใด,
สายพันธุ์ใด, อายุเท่าไร และใช้ model/fallback ใด พร้อมทดสอบเส้นทางจริง
Dashboard → Cloud → Edge → Cloud → Dashboard

## ขอบเขต

- เพิ่ม Batch binding administration และสถานะ sync/stale ใน Dashboard
- แสดง Batch, breed, age, model package/version, prediction mode และ fallback reason
  ใน Sessions/detail page
- แสดง unassigned/ambiguous เป็นสถานะที่ actionable
- เพิ่ม API schemas/clients และ read-model projection สำหรับ provenance ใหม่
- เพิ่ม Docker Compose smoke และ Playwright E2E ของ critical path

## Acceptance Criteria

- [x] ผู้ใช้สร้าง Batch และ binding แล้วเห็น Edge sync state สำเร็จ
- [x] capture จาก bound station แสดง Station/Batch/breed/age/prediction mode/weight
  และ fallback status ใน Dashboard
- [x] unassigned session แสดงเหตุผลและแนวทางผูก Batch ไม่ใช่ข้อมูลว่างเงียบ ๆ
- [x] Dashboard แสดง `SHADOW_STUB` และ `NO_SITE_SUBSCRIPTION` สำหรับผล fallback;
  ไม่อ้างว่าเป็น breed-specific package
- [x] E2E ผ่านบน clean dev database/volume ที่มี migration ครบ
- [x] `docker compose up -d --build` เฉพาะ services ที่เกี่ยวข้อง แล้ว health/smoke ผ่าน

## ผลการยืนยัน runtime (2026-09-24 ถึง 2026-09-25)

- สร้าง device และ WeighVision station จริง, bind กับ active Batch แล้ว Edge
  policy lookup resolve context revision `2` ได้
- mock capture สร้าง session `bces-e2e-b4a745c5-594f-41ce-bf39-a4629334af7a` และ
  inference `2.94 kg`; Cloud read-model รับ session/inference พร้อม Station,
  Batch, breed, อายุ 16 วัน และ `NO_SITE_SUBSCRIPTION`
- ตรวจ UI จาก Vite source ที่ `/weighvision/sessions`: มีคอลัมน์ Station,
  Batch Context และ Model Status; แถว E2E แสดงข้อมูลข้างต้นครบ
- rebuild image เฉพาะ `dashboard-web`, recreate แบบ `--no-deps` และ health check
  ของ `farmiq-dashboard-web` ผ่าน; `http://localhost:5142` ตอบ HTTP 200

### หลักฐานการยืนยัน final (2026-09-25)

- Dashboard login ใน E2E ด้วย `admin@farmiq.com` สำเร็จ และหน้า Sessions
  แสดง `wv-001`, `st-001`, `batch-e2e-t001`, breed, age 21 วัน, `5.16 kg`,
  `SHADOW_STUB` และ `NO_SITE_SUBSCRIPTION`
- สร้าง session ที่ไม่มี binding (`unassigned-e2e-76aed25a`) ผ่าน Edge และ
  read-model/BFF ส่งถึง Dashboard; UI แสดง `UNASSIGNED` พร้อมข้อความ
  **Bind this station in Batches & Flocks**
- Dashboard มี Batch create/bind control ที่เรียก BFF binding API; runtime E2E
  ยืนยัน Batch create revision `1` และ binding revision `2` บน resources
  `bces-e2e-*` เท่านั้น
- rebuild แบบ no-cache เฉพาะ `dashboard-web` ผ่าน และ Dashboard/Cloud BFF/
  Tenant Registry/Identity/Read-model/Edge session/Inference/Sync/Policy health
  ตอบ HTTP `200`. mock IoT ไม่มี health endpoint; ถูกยืนยันจาก capture E2E
  ที่สร้าง inference สำเร็จแทน

รายละเอียด isolation, minimal service set, ports และ acceptance flow อยู่ที่
[`BCES_CLEAN_VOLUME_E2E_SPEC.th.md`](../BCES_CLEAN_VOLUME_E2E_SPEC.th.md)

## แผนทดสอบเส้นทาง

```text
1. Login Dashboard และสร้าง active batch + device/station binding
2. ตรวจ Cloud outbox และ Edge batch context cache
3. ส่ง mock IoT image
4. ตรวจ Edge session และ inference provenance
5. Trigger Edge sync
6. ตรวจ Cloud read model และ Dashboard session page
7. ทดสอบ Cloud unavailable โดยใช้ cache ที่ยังไม่หมดอายุ
```

## การเปลี่ยนแปลงเชิงเทคนิค

| พื้นที่ | งาน |
|---|---|
| Dashboard React | binding UI, session provenance UI, error states |
| BFF/read model | response schemas และ projection fields |
| Playwright | create/bind/capture/display critical flow |
| Docker/runbook | minimal service profile, migration และ smoke commands |

## Deployment / Rollback

- deploy API/read-model additive ก่อน UI
- UI ซ่อน field ใหม่ได้เมื่อ downstream version ยังไม่รองรับ
- rollback UI ได้โดยไม่กระทบ session/inference records ที่มี provenance ใหม่
- E2E stack ต้องใช้เฉพาะ local `bces-e2e-*` resources และ explicit E2E database
  hosts; ไม่มีขั้นตอนใดเชื่อมต่อหรือแก้ไข Production

## ความเสี่ยง

| ความเสี่ยง | การลดความเสี่ยง |
|---|---|
| Docker stack ใช้ RAM สูง | ระบุ minimal profile และ service dependency ชัดเจน |
| test flaky จาก async sync | poll health/state ด้วย timeout และ correlation ID |

## Revalidation 2026-09-28

Cloud/Edge Compose config ผ่านและ minimum `bces-e2e-*` stack healthy. Dashboard
Vite production build ผ่าน; browser login/list/detail แสดง Station, Batch,
ROSS-308/day 24, 5.16 kg, SHADOW_STUB และ NO_SITE_SUBSCRIPTION. แก้ list query
ที่ค้าง empty state จาก `initialData: []`. Full Dashboard type-check/Vitest ยังมี
baseline blockers นอก BCES ซึ่งบันทึกใน validation report.
