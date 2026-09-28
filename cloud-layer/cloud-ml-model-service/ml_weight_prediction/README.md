# การทำนายน้ำหนักไก่รายตัวของ FarmIQ

โฟลเดอร์นี้มีแนวทางโมเดล XGBoost อยู่ 2 แบบที่แยกหน้าที่กันชัดเจน:

1. โมเดลจัดสรรน้ำหนักแบบ weakly supervised สำหรับกรณีไก่หลายตัวอยู่บนเครื่องชั่งเดียวกัน
2. โมเดลทำนายน้ำหนักรายตัวที่ผ่านการปรับเทียบ ซึ่งจะใช้ได้ในอนาคตเมื่อมี label น้ำหนักจริงของไก่แต่ละตัว

ระบบตั้งใจไม่ใช้ `group_total` หรือค่าน้ำหนักเฉลี่ยต่อไก่ที่คำนวณประมาณขึ้นมาเป็น label สำหรับฝึกโมเดลรายตัว แม้ข้อมูลเหล่านี้จะมีประโยชน์ต่อการตรวจสอบยอดรวมเชิงปฏิบัติการ แต่ไม่ใช่ label ที่ถูกต้องสำหรับตัวทำนายน้ำหนักรายตัว

## สถานะปัจจุบัน

ไฟล์ `metadata.txt` มีตัวอย่างการจับภาพ 1 ครั้ง พบไก่ 4 ตัว และมีน้ำหนักรวมจากเครื่องชั่งเพียง 1.0 กก. ดังนั้นข้อมูลนี้เป็นเพียง **ตัวอย่าง feature ที่ยังไม่มี label** ไม่ใช่ข้อมูลฝึกสอน

ยังไม่สามารถสรุป metric ความแม่นยำระดับรายตัว หรือตัดสินใจใช้งานจริงใน production ได้จากข้อมูลนี้

อย่างไรก็ตาม telemetry ของการจับภาพนี้สามารถใช้ทดลองแนวทาง **weak allocation** ได้ โดยให้ไก่แต่ละตัวที่ผ่านเกณฑ์คุณภาพมี pseudo target เริ่มต้นเท่ากับน้ำหนักรวมของกลุ่มหารด้วยจำนวนไก่ที่ผ่านเกณฑ์ ตอนทำนาย ระบบจะนำคะแนนดิบของแต่ละตัวมาปรับสัดส่วนให้ผลรวมเท่ากับน้ำหนักรวมที่อ่านได้จากเครื่องชั่ง

วิธีนี้รักษาน้ำหนักรวมของกลุ่มได้ แต่ **ไม่ได้ยืนยันความถูกต้องของน้ำหนักรายตัว**

## ข้อมูลที่ต้องมีเพื่อ train โมเดลน้ำหนักรายตัว

วางไฟล์ CSV ที่ `data/labels/individual_weights.csv` โดยมีหนึ่งแถวต่อไก่หนึ่งตัว:

```text
record_id,actual_weight_g,weight_stable,weight_label_type,camera_id,batch_id,breed,sex,age_days
e945fe65-69b4-5fd2-af23-02a59258645b,250,true,individual,stereo-01,B20260917,Arbor Acres Plus,male,28
```

`record_id` ต้องตรงกับ `per_chicken_records[].record_id` ใน metadata ของการจับภาพ ให้ใช้เฉพาะ capture ที่มีไก่ตัวเดียวบนเครื่องชั่ง หรือกรณีที่จับคู่ track ของไก่กับน้ำหนักจากเครื่องชั่งได้อย่างชัดเจน

ห้ามสร้างค่า `actual_weight_g` ด้วยการนำน้ำหนักรวมของกลุ่มไปหารจำนวนไก่

## เงื่อนไขมาตรฐานการเจริญเติบโต

ก่อน train และก่อนทำนาย ระบบจะจับคู่ `breed`, `sex` และ `age_days` กับตาราง Aviagen Arbor Acres Plus ทุกวันอายุ 1–56 วัน แล้วเพิ่ม `standard_weight_g`, `standard_adg_g_per_day` และ `standard_fcr` เป็น feature ไฟล์มาตรฐานแยกตามเพศอยู่ที่ `docs/performance_standards/arbor_acres_plus/`.

โมเดลรายตัวเรียนรู้ค่าน้ำหนักที่ต่างจากน้ำหนักมาตรฐาน (`actual_weight_g - standard_weight_g`) และนำค่านั้นกลับไปรวมกับน้ำหนักมาตรฐานตอนทำนาย ผลลัพธ์จึงมี `growth_performance_pct` สำหรับเทียบประสิทธิภาพจริงกับเส้นมาตรฐานของสายพันธุ์และเพศนั้น หากไม่ระบุข้อมูลดังกล่าว หรืออายุ/สายพันธุ์ยังไม่อยู่ในตาราง ระบบจะตอบ `REJECTED_GROWTH_STANDARD` แทนการเดา

มาตรฐานที่จัดส่งใน package ปัจจุบันรองรับเฉพาะ `Arbor Acres Plus` และ `as_hatched`, `male`, `female` การเพิ่มสายพันธุ์ใหม่ต้องเพิ่มมาตรฐานที่ได้รับอนุมัติและฝึกโมเดลใหม่ ไม่ควร map ไปใช้เส้น Arbor Acres โดยอัตโนมัติ

ตัวอย่าง event ที่ส่งให้โมเดลรายตัวต้องมีอย่างน้อย:

```json
{"breed":"Arbor Acres Plus","sex":"male","age_days":28,"confidence":0.92}
```

พร้อม geometry feature เดิมทั้งหมด รายการ `breed`, `sex` และ `age_days` ต้องอยู่ใน event ระดับเดียวกับ feature ของไก่ สำหรับ weak allocation ให้ใส่ทั้งสาม field ที่ event ระดับกลุ่ม หรือกำหนดราย detection เพื่อ override ได้

## คำสั่งใช้งาน

ใช้ Python environment ที่ติดตั้ง package ตาม `requirements.txt`:

```powershell
pip install -r requirements.txt
python scripts/build_dataset.py --metadata metadata.txt --labels data/labels/individual_weights.csv --output data/processed/training_features.csv --audit-output reports/data_audit.csv --height-min-mm <approved-min> --height-max-mm <approved-max>
python scripts/train.py --dataset data/processed/training_features.csv --output-dir artifacts/candidate
python scripts/package_model.py --artifact-dir artifacts/candidate --output-dir artifacts/edge
python scripts/edge_predict.py --package-dir artifacts/edge --event edge_event.json
python scripts/build_weak_dataset.py --captures docs/sample_data/session_capture_metadata.csv --output data/processed/weak_group_features.csv --audit-output reports/weak_group_audit.csv
python scripts/train_weak_xgboost.py --dataset data/processed/weak_group_features.csv --output-dir artifacts/weak-candidate --allow-within-day-holdout
python scripts/package_model.py --artifact-dir artifacts/weak-candidate --output-dir artifacts/weak-edge
python scripts/edge_allocate.py --package-dir artifacts/weak-edge --event group_event.json
```

`<approved-min>` และ `<approved-max>` คือช่วงความสูงที่ผ่านการอนุมัติสำหรับกล้อง/ฟาร์ม ใช้เพื่อควบคุมคุณภาพของข้อมูล ค่าทั้งสองต้องมาจากประชากรข้อมูลที่มี label แล้ว ตัวอย่างปัจจุบันยังไม่เพียงพอสำหรับกำหนดค่าเอง

คำสั่ง `build_dataset.py` จะสร้าง audit report แม้ไม่มีแถวข้อมูลที่ผ่านเกณฑ์สำหรับ train ส่วน `train.py` ใช้การแบ่งชุดข้อมูลตามลำดับเวลาและแยกกลุ่ม capture ออกจากกัน และจะหยุดพร้อมข้อความอธิบายจนกว่าจะมีข้อมูลที่ติด label เพียงพอ

`--allow-within-day-holdout` มีไว้เพื่อทดสอบ flow กับข้อมูลตัวอย่างปัจจุบันเท่านั้น ผลลัพธ์ยังใช้สำหรับ production ไม่ได้ เพราะมี 221 session จากวันเดียว และ target เป็น pseudo label จากค่าเฉลี่ยน้ำหนักของกลุ่ม

### ทดสอบชุด export `session_id_20260919`

ชุดนี้มี `session_capture_metadata`, `weight_sessions`, `inference_results`, `media_objects` และรูปตัวอย่าง โดย `session_id` map ระหว่าง `session_capture_metadata` กับ `weight_sessions` ได้ตรงกัน แต่ label ใน metadata เป็น `group_total` หลายตัวต่อ session จึงทดสอบได้เฉพาะ weak allocation ไม่ใช่ individual regression

metadata ที่ export ในวันดังกล่าวยังไม่มี `breed`, `sex` และ `age_days` ขณะสร้าง dataset ให้ส่งค่า context ของ flock อย่างชัดเจน ชุดนี้ผู้ใช้ยืนยันเพศผู้และเริ่มเลี้ยงวันที่ 2026-09-09 จึงใช้อายุ 10 วัน ณ วันที่จับภาพ 2026-09-19 (นับ elapsed days):

> ไฟล์ต้นฉบับใน `docs/performance_standards/arbor_acres_plus/` เก็บสถานะ `DRAFT` ไว้เป็น reference โดย pipeline จะใช้เฉพาะสำเนาที่ได้รับการอนุมัติใน `approved/` เท่านั้น

```powershell
python scripts/build_weak_dataset.py `
  --captures docs/sample_data/session_id_20260919/metadata/session_capture_metadata-1789967494963.csv `
  --performance-standard docs/performance_standards/arbor_acres_plus/approved/Arbor_Acres_Plus_Male_Performance_Standard.xlsx `
  --default-breed "Arbor Acres Plus" `
  --default-sex male `
  --default-age-days 10 `
  --output data/processed/session_20260919_weak_features.csv `
  --audit-output reports/session_20260919_weak_audit.csv

python scripts/train_weak_xgboost.py `
  --dataset data/processed/session_20260919_weak_features.csv `
  --output-dir artifacts/session_20260919_weak_candidate `
  --allow-within-day-holdout
```

ค่า default ใช้เฉพาะเมื่อ field นั้นไม่มีใน detection/capture metadata และไม่แก้ไขไฟล์ export ต้นฉบับ การอ้างอิงมาตรฐานสายพันธุ์ไม่สามารถอนุมานเพศหรืออายุของ flock ได้เอง จึงห้ามใช้ค่าในตัวอย่างโดยไม่ยืนยันกับข้อมูลหน้างาน

อ่าน [แผนการส่งมอบโมเดล](docs/MODEL_DELIVERY_PLAN.md) เพื่อดู acceptance gate, การประเมินแบบ shadow, การ rollback และข้อมูลที่ยังต้องขอจากฟาร์ม

สำหรับ capture ที่มีไก่หลายตัวอยู่บนเครื่องชั่งเดียวกัน ให้ดู [แผน weak supervision สำหรับน้ำหนักกลุ่ม](docs/WEAKLY_SUPERVISED_GROUP_SCALE_XGBOOST_PLAN.md) รายการแก้ไขที่จำเป็นของ edge services อยู่ใน [integration contract ของ edge layer](docs/EDGE_LAYER_GROUP_ALLOCATION_INTEGRATION.md)
# Shadow integration

For the observation-only Arbor Acres candidate integration, see
[implementation plan and runbook](docs/SHADOW_ALLOCATION_IMPLEMENTATION.md) and
[executed test evidence](docs/SHADOW_ALLOCATION_TEST_REPORT.md).
This mode never claims validated individual accuracy and does not feed decisions.
