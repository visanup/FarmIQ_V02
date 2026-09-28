# Broiler performance standards

ใช้โฟลเดอร์นี้เก็บมาตรฐานการเติบโตที่ได้รับอนุมัติสำหรับแต่ละสายพันธุ์และเพศ

## วิธีเพิ่มสายพันธุ์

1. คัดลอก `Broiler_Performance_Standard_Template.xlsx` และตั้งชื่อให้สื่อสายพันธุ์และรุ่นเอกสาร เช่น `Cobb_500_Performance_2026.xlsx`
2. กรอกข้อมูลหนึ่งแถวต่อสายพันธุ์ + เพศ + อายุ (วัน) ในชีต `Standards`
3. กำหนด `status` เป็น `APPROVED` เฉพาะข้อมูลที่ผ่านการอนุมัติแล้ว
4. เก็บแหล่งอ้างอิงและรุ่นเอกสารใน `source` และ `source_version`
5. ส่งชื่อไฟล์มาตรฐานผ่าน `--performance-standard` เมื่อสร้าง dataset และ package โมเดล

อย่าใช้ตารางของสายพันธุ์หนึ่งแทนอีกสายพันธุ์หนึ่ง ระบบจะค้นหาค่า `breed` ตามที่ระบุในไฟล์ template โดยตรง และปฏิเสธข้อมูลที่ไม่มีมาตรฐานตรงกัน

## คอลัมน์ที่ต้องกรอก

- `breed`, `sex`, `age_days`, `body_weight_g`, `adg_g_per_day`, `fcr`
- `source`, `source_version`, `effective_date`, `approved_by`, `status`

ค่า `sex` ใช้ `as_hatched`, `male` หรือ `female` อายุเริ่มที่ 1 วัน และต้องไม่มีรายการซ้ำของ `breed` + `sex` + `age_days`

ตัวอ่านมาตรฐานจะรับ Excel ที่มีชีต `Standards` ตาม template นี้ และอ่านเฉพาะแถว `APPROVED` เท่านั้น โดยรองรับชื่อสายพันธุ์ใหม่ เช่น `Cobb 500` โดยไม่ต้องเพิ่มชื่อสายพันธุ์ลงในโค้ดก่อน
