# AI Model Field Findings - 2026-07-20

## Scope
สรุปปัญหาที่เจอจริงจากการ evaluate object detection/segmentation ของ dataset `Chicken Segmentation.v4i.yolo26` และวิธีที่ทีมแก้ในระดับ evaluation, dataset, และ training pipeline

อ้างอิงการ audit จริงจาก:
- `iot-layer/weight-vision-train-model-yolo26/runs/label_audit_20260720/audit_summary.json`
- `iot-layer/weight-vision-train-model-yolo26/runs/label_audit_20260720/sample_manifest.json`
- `iot-layer/weight-vision-train-model-yolo26/runs/eval_search/conf_scan_summary.json`
- `iot-layer/weight-vision-train-model-yolo26/runs/eval_search/conf_iou_scan_summary.json`

## Problem Found
### 1. Background ใน confusion matrix ไม่ใช่ class จริง
- `True = background` คือ false positive
- `Predicted = background` คือ false negative
- ปัญหาจริงไม่ใช่การเอา background ออกจากรูป แต่ต้องหาสาเหตุว่าทำไม model ยังทายเกินหรือทายหลุด

### 2. NCK ยังสลับกับ background สูง
- audit ที่ `conf=0.40`, `nms_iou=0.45`, `match_iou=0.50`
- `NCK ground truth = 3554`
- `NCK false negative = 614`
- `NCK false positive = 504`

### 3. สาเหตุหลักของ NCK -> background
- `56.2%` ของ NCK อยู่ติดขอบภาพ
- `33.2%` ของ NCK มีขนาดเล็กกว่า `0.5%` ของภาพ
- `67.7%` ของ NCK มีขนาดเล็กกว่า `1%` ของภาพ
- `18.5%` ของ NCK อยู่ในภาพที่ object ซ้อนหรือเบียดกัน
- ในกลุ่ม false negative:
  - `56.5%` ติดขอบภาพ
  - `52.8%` เป็น object เล็กมาก
  - `21.5%` อยู่ในฉาก crowded

ข้อสรุป:
`NCK -> background` เกิดจากภาพยากจริง เช่น object เล็ก, อยู่ริมภาพ, ถูกบัง, contour ไม่ชัด และ segmentation match ยาก

### 4. สาเหตุของ background -> NCK
- `38.9%` ของ NCK false positive อยู่ใกล้ขอบภาพ
- `46.0%` ของ NCK false positive มี confidence ตั้งแต่ `0.6` ขึ้นไป

ข้อสรุป:
ไม่ใช่แค่ตั้ง confidence threshold ต่ำ แต่มีเคสที่ model มั่นใจผิดจริง และมี bias ไปทางทาย NCK เกินในบริเวณขอบภาพหรือ object ซ้อนกัน

### 5. มีสัญญาณเรื่อง label quality / annotation consistency
- พบ `invalid label rows = 15`
- จาก sample audit มีหลายภาพที่เห็นตัวไก่จริง แต่ GT ไม่ครอบตำแหน่งหรือ contour ในแบบที่ model ทาย
- จึงมีโอกาสที่บาง false positive จะเป็นกรณี `ภาพมี object จริง แต่ GT ไม่ครบ` ไม่ใช่ model ผิดทั้งหมด

## What The Team Fixed
### 1. แก้ evaluation ให้ถูกหลัก
- แยก evaluation ออกเป็น 2 ชั้น
- `standard validation` สำหรับ `mAP@0.5` และ `mAP@0.5:0.95`
- `operational IoU matching` สำหรับ `TP/FP/FN/precision/recall/F1`
- เพิ่มการอ่าน confusion matrix ให้ตีความ `background` ถูกต้อง
- เพิ่ม `evaluation-report.json` และ `evaluation-summary.md`

### 2. เพิ่มการควบคุม threshold ให้ตรวจสอบได้จริง
- เพิ่ม `--standard-val-conf`
- เพิ่ม `--standard-val-iou`
- ทำให้ `confusion_matrix.png` เปลี่ยนตาม threshold ที่ตั้งจริง ไม่ใช่เปลี่ยนเฉพาะ operational report

### 3. ปรับ training pipeline เพื่อแก้ class imbalance
- เพิ่ม `--auto-balance`
- เพิ่ม class weighting
- เพิ่ม `copy_paste`
- เพิ่ม oversampling สำหรับ class ที่ขาด เช่น `CK-S`
- ช่วยลด bias จาก dataset imbalance ในรอบ train ถัดไป

## What The Team Should Do Next
### Dataset / Label
- cleanup `15 invalid label rows`
- review ภาพ NCK ที่ติดขอบ, ถูกบัง, หรือซ้อนกัน
- ทำ annotation policy ให้สม่ำเสมอ เช่นกรณีเห็นแค่บางส่วนจะ label หรือไม่ label
- shortlist ภาพที่สงสัยว่า `GT ไม่ครบ` เพื่อรีวิวซ้ำกับทีม labeling

### Model / Training
- retrain ด้วย dataset ที่ balance กว่าเดิม
- ใช้ผลจาก `auto-balance` กับรอบ train ใหม่
- พิจารณาเพิ่ม `imgsz` หรือ crop/tiling ถ้า object เล็กมากเป็น pattern หลัก
- ใช้ threshold ที่สมดุลกว่าระหว่าง false positive และ false negative

### Evaluation / Governance
- ใช้ `standard validation` และ `operational IoU matching` คู่กันทุกครั้ง
- ห้ามสรุปผลจาก confusion matrix ที่ซ่อน background อย่างเดียว
- ใช้ sample audit images ตรวจว่าปัญหาเป็น model issue หรือ label issue ก่อนสรุป

## Recommended Narrative For Team
ปัญหาที่เจอจริงในรอบนี้ไม่ใช่แค่ `background ยังอยู่ใน confusion matrix` แต่คือ model ยังพลาด NCK ในสภาพภาพที่ยาก และบางส่วนของ dataset มีความเสี่ยงเรื่อง label consistency

สิ่งที่ทีมแก้แล้วคือ:
- แก้ evaluation ให้ถูกหลัก
- เพิ่ม threshold control ให้ confusion matrix ตรงกับค่าที่ใช้จริง
- เพิ่ม auto-balance และ class weighting ใน training pipeline

สิ่งที่ต้องทำต่อคือ:
- cleanup label
- review ภาพยาก
- retrain ด้วยข้อมูลที่สมดุลและสะท้อน field condition จริงมากขึ้น
