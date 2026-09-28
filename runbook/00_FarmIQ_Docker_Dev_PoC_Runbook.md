# FarmIQ: build และ up Docker สำหรับคืนนี้

อัปเดต 2026-09-21 — เลือกหนึ่งในสองคู่มือ:

1. [Dev: IoT + Edge + Cloud เครื่องเดียว](DEV_SINGLE_MACHINE.md) — Windows PowerShell, mock ก่อนต่อ hardware
2. [PoC: IoT หนึ่งเครื่อง + Edge/Cloud อีกเครื่อง](POC_TWO_MACHINES.md) — Ubuntu Bash, IP ตาม network runbook เดิม

คู่มือสองฉบับนี้ใช้ **build จาก source ปัจจุบัน** พร้อม XGBoost shadow และใช้
Compose base + dev + override ที่แนบไว้สำหรับ Dev/PoC เท่านั้น ไม่ใช่คู่มือ production release
หรือ offline `docker load` แบบ HTML เดือนสิงหาคม อ่าน HTML เดิมเมื่อต้องการรายละเอียด
network/กล้อง/AnyDesk หรือกระบวนการ offline update

| เครื่อง/บริการ | Dev | PoC |
|---|---|---|
| IoT | เครื่องเดียวกับ Edge/Cloud | 192.168.1.121 |
| Edge + Cloud | เครื่อง Dev | 192.168.1.120 |
| กล้องซ้าย/ขวา | mock หรือ hardware ที่ตั้งค่าแล้ว | 192.168.1.199 / 192.168.1.200 |
| Network กล้อง IoT | ตาม hardware จริง | Ethernet 192.168.1.122/32 + host routes ตาม HTML 03 |
| Repo | E:\FarmIQ_V02 | /srv/FarmIQ_V02 |

ไฟล์ `compose/` เป็น override ที่ใช้จริงกับคำสั่งในคู่มือ:

- `cloud.local.yml`: ย้าย published port ของ cloud-hybrid-router จาก 5141 เป็น 5149
  เพราะ 5141 ใช้โดย Edge PostgreSQL; Datadog เป็น optional profile
- `edge.shadow.yml`: image/dependencies XGBoost, model mount read-only, Python healthcheck,
  host gateway สำหรับ Ubuntu, policy context และตัด dependency ของ forwarder ที่ชี้ mock cloud
- `iot.endpoints.yml`: endpoint จาก container IoT ไปเครื่อง Edge ตาม topology

ใช้ Compose 2.24.4 ขึ้นไปที่รองรับ `!override` และตรวจ `config --quiet` ก่อน build
ทั้ง cloud และ edge ต้องใช้ project name เดิม (`cloud-layer`, `edge-layer`, `iot-layer`)
หากของเครื่องจริงใช้ชื่ออื่นให้ใช้ชื่อนั้นทุกคำสั่งเพื่อรักษา volumes เดิม
ไม่ใช้ `down -v`, ไม่ reset/seed ฐานข้อมูลเดิม และไม่ใช้ `migrate dev` กับข้อมูลที่ต้องเก็บ

ข้อแก้ไขจากคำอธิบายก่อนหน้า: DB ของ Edge เมื่อ merge base + dev คือ
`${POSTGRES_DB:-farmiq}` ใน **Edge postgres** ไม่ใช่ `edge_vision_inference` เสมอไป
สองตาราง shadow ถูก ensure ตอน startup แม้ปิด flag; role ของ service ต้องมีสิทธิ์
หรือให้เจ้าของ DB apply SQL ล่วงหน้าในฐานข้อมูลเดียวกับ `DATABASE_URL`

สถานะการตรวจคำสั่งและข้อจำกัด: [VALIDATION.md](VALIDATION.md)
