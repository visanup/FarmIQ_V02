# FarmIQ: Feature Specification สำหรับทำนายน้ำหนักไก่รายตัวด้วย XGBoost

เอกสารฉบับนี้กำหนดข้อมูล input, feature engineering และกติกาคุณภาพข้อมูล สำหรับสร้างโมเดล XGBoost ที่ทำนายน้ำหนักไก่รายตัวจากผล YOLO instance segmentation และ stereo/depth measurement ของระบบ FarmIQ

## 1. เป้าหมายของโมเดล

- หน่วยทำนาย: ไก่ 1 ตัว ต่อ 1 แถวข้อมูล
- โมเดล: `XGBRegressor`
- Target / label: `actual_weight_g` — น้ำหนักจริงของไก่ตัวนั้น หน่วยกรัม
- Output: `predicted_weight_g` พร้อมสถานะคุณภาพการทำนาย

> ข้อจำกัดของ metadata ปัจจุบัน: ไฟล์ตัวอย่างระบุ `weight_label_type: group_total` และ `group_weight_kg: 1.0` สำหรับไก่ 4 ตัว จึงยังไม่ใช่ label รายตัว ค่า `estimated_weight_per_chicken_kg: 0.25` เกิดจากการหารเฉลี่ย 1.0 / 4 และห้ามใช้แทน `actual_weight_g` ในการ train โมเดลรายตัว

## 2. หนึ่งแถวข้อมูลต่อหนึ่งตัว

ใช้ `per_chicken_records[]` เป็นฐานของ training dataset โดยให้หนึ่ง `detection_index` เป็นหนึ่งแถว และเพิ่ม label ที่ชั่งจริงทีละตัว

```json
{
  "record_id": "e945fe65-69b4-5fd2-af23-02a59258645b",
  "session_id": "20260917_020955",
  "detection_index": 2,
  "actual_weight_g": 250
}
```

`actual_weight_g` ต้องมาจากขั้นตอนชั่งไก่ตัวเดียวและจับคู่กับภาพ/track ของไก่ตัวเดียวกันอย่างชัดเจน

## 3. Feature ที่ต้องส่งเข้าโมเดล

### 3.1 Feature หลัก

| Feature model | แหล่งข้อมูลปัจจุบัน | หน่วย | การใช้งาน |
|---|---|---:|---|
| `area_mm2` | `area_mm2` / `area_xy_mm2` | mm² | ขนาดพื้นที่ mask บนระนาบ XY; เป็น feature หลัก |
| `length_mm` | `object_length_mm` / `length_mm` | mm | ความยาวลำตัวจาก rotated rectangle |
| `width_mm` | `object_width_mm` / `width_mm` | mm | ความกว้างลำตัว |
| `height_mm` | `height_mm` | mm | ความสูงจาก stereo depth; ใช้หลังผ่าน quality check |
| `depth_mm` | `average_depth_mm` / `depth_mm` | mm | ระยะถึงกล้อง ใช้ชดเชยความคลาดเคลื่อนจาก perspective |
| `confidence` | `confidence_score` / `confidence` | 0–1 | คุณภาพ detection/segmentation |

### 3.2 Feature ที่คำนวณเพิ่ม

| Feature model | สูตร | จุดประสงค์ |
|---|---|---|
| `volume_proxy_area_height_mm3` | `area_mm2 × height_mm` | ตัวแทนปริมาตรจาก mask และความสูง |
| `volume_proxy_lwh_mm3` | `length_mm × width_mm × height_mm` | ตัวแทนปริมาตรทรงกล่อง ใช้เป็น feature เปรียบเทียบ |
| `length_width_ratio` | `length_mm / width_mm` | บอกสัดส่วน/ท่าทางของไก่ |
| `bbox_width_px` | `x2 - x1` จาก `bbox_xyxy` | ลักษณะขนาดในภาพ |
| `bbox_height_px` | `y2 - y1` จาก `bbox_xyxy` | ลักษณะขนาดในภาพ |
| `bbox_area_px` | `bbox_width_px × bbox_height_px` | ใช้เป็นข้อมูลประกอบพื้นที่ mask |
| `bbox_aspect_ratio` | `bbox_width_px / bbox_height_px` | บอกแนววางตัวและรูปทรง |
| `mask_fill_ratio` | `mask_area_px / bbox_area_px` | ตรวจรูปทรง mask และการถูกบัง |
| `centroid_x_norm` | `pixel_xy[0] / image_width` | ชดเชยตำแหน่งที่มี perspective ต่างกัน |
| `centroid_y_norm` | `pixel_xy[1] / image_height` | ชดเชยตำแหน่งที่มี perspective ต่างกัน |
| `is_height_outlier` | 0 หรือ 1 ตามกติกา QC | แจ้งโมเดลว่าค่า height มีโอกาสผิดปกติ |

## 4. ชุด Feature เริ่มต้นที่แนะนำ

เริ่ม train รอบแรกด้วย feature เหล่านี้ก่อน เพื่อให้ตรวจสอบสาเหตุของความคลาดเคลื่อนได้ง่าย

```text
area_mm2
length_mm
width_mm
height_mm
depth_mm
confidence
volume_proxy_area_height_mm3
volume_proxy_lwh_mm3
length_width_ratio
bbox_area_px
bbox_aspect_ratio
mask_fill_ratio
centroid_x_norm
centroid_y_norm
is_height_outlier
```

ไม่จำเป็นต้อง normalize feature สำหรับ XGBoost แต่ต้องรักษาหน่วยให้คงที่ทุก session: น้ำหนักเป็นกรัม, มิติเป็นมิลลิเมตร, พื้นที่เป็นตารางมิลลิเมตร

## 5. ค่าจากไฟล์ตัวอย่าง

ตัวอย่างนี้พบไก่ใน ROI จำนวน 4 ตัว และมีน้ำหนักรวม `1.0 kg` เท่านั้น จึงใช้เป็นข้อมูล feature ได้ แต่ยังห้ามนำไป train target น้ำหนักรายตัว

| detection_index | area_mm2 | length_mm | width_mm | height_mm | depth_mm | confidence |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5981.33 | 87.41 | 87.40 | 67.37 | 947.56 | 0.814 |
| 2 | 8109.52 | 171.08 | 74.33 | 22.22 | 992.71 | 0.909 |
| 3 | 5898.00 | 94.21 | 73.18 | 62.45 | 952.48 | 0.900 |
| 4 | 6847.67 | 118.04 | 73.94 | 65.50 | 949.43 | 0.855 |

ข้อสังเกต: `height_mm` ของ detection 2 เท่ากับ 22.22 mm ขณะที่ตัวอื่นอยู่ราว 62–67 mm จึงควรติดธง `is_height_outlier = 1` หรือพิจารณาตัดแถวดังกล่าวจาก training หากตรวจสอบแล้วว่ามีปัญหาที่ depth/mask

## 6. ข้อมูลที่ห้ามใช้เป็น Feature

| Field | เหตุผล |
|---|---|
| `scale_weight_kg`, `group_weight_kg` | เป็นค่าคำตอบจากตราชั่ง จึงเกิด data leakage |
| `estimated_weight_per_chicken_kg` | เป็นการหารเฉลี่ยจากน้ำหนักรวม ไม่ใช่ label จริงรายตัว |
| `weight_label_type` | ใช้ตรวจคุณภาพ label ได้ แต่ไม่ใช่ข้อมูลรูปร่างของไก่ |
| `record_id`, `session_id`, `image_id`, `detection_index`, `locked_track_id` | เป็น identifier ไม่ใช่คุณลักษณะเชิงกายภาพ |
| `class_id` | ในข้อมูลนี้เป็น class เดียวทุกแถว จึงไม่มีประโยชน์ต่อโมเดล |
| `mask_xy`, `mask_path` | เป็นข้อมูลดิบขนาดไม่คงที่ ให้แปลงเป็น feature เช่นพื้นที่/อัตราส่วนก่อน |
| `focal_length_px`, `baseline_mm`, `rms_stereo` | ไม่ควรใช้เมื่อกล้องและ calibration ชุดเดิม เพราะค่าแทบไม่เปลี่ยน |

## 7. Quality Gate ก่อนสร้างแถว training

เก็บหรือ train เฉพาะแถวที่ผ่านเงื่อนไขต่อไปนี้

- `confidence >= 0.80` ตาม acceptance gate ปัจจุบัน
- อยู่ภายใน ROI และ mask ไม่ถูกตัดขอบ ROI/ขอบภาพอย่างมีนัยสำคัญ
- ตราชั่งนิ่ง: `weight_stable = true`
- `weight_label_type = individual` สำหรับชุดฝึกน้ำหนักรายตัว
- มิติและ depth เป็นค่าบวก ไม่เป็น `null` หรือ NaN
- ตรวจ outlier ของ `height_mm`, `area_mm2`, `length_mm`, `width_mm` ด้วยช่วงที่ได้จากข้อมูลจริงหรือ IQR ต่อ batch

เก็บแถวที่ไม่ผ่านไว้ในตาราง audit เพื่อใช้วิเคราะห์และปรับปรุง capture/segmentation แต่ไม่ต้องใช้ train ในรอบแรก

## 8. Schema แนะนำสำหรับตาราง Training

```text
record_id
session_id
captured_at
camera_id
batch_id
age_days

actual_weight_g                         # target, ต้องเป็นค่าน้ำหนักจริงรายตัว
area_mm2
length_mm
width_mm
height_mm
depth_mm
confidence
volume_proxy_area_height_mm3
volume_proxy_lwh_mm3
length_width_ratio
bbox_width_px
bbox_height_px
bbox_area_px
bbox_aspect_ratio
mask_fill_ratio
centroid_x_norm
centroid_y_norm
is_height_outlier
is_mask_clipped
quality_pass
```

`camera_id`, `batch_id` และ `age_days` เป็น optional แต่มีประโยชน์มากเมื่อข้อมูลครอบคลุมหลายกล้อง หลายรุ่นไก่ หรือหลายช่วงอายุ

## 9. การเก็บ Label ที่ถูกต้อง

1. วางไก่เพียง 1 ตัวบนแท่นชั่งในแต่ละ capture
2. รอให้ตราชั่งนิ่ง แล้วบันทึกน้ำหนักเป็นกรัม
3. บันทึกภาพ stereo และ metadata ในจังหวะเดียวกัน
4. จับคู่ `actual_weight_g` กับ `detection_index` หรือ `locked_track_id` ของไก่ตัวนั้น
5. บันทึก batch, อายุ (วัน), สายพันธุ์ และเพศ หากมี

หากต้องใช้ภาพหลายตัวบนแท่นเดียวกันในอนาคต สามารถใช้โมเดลรายตัวที่ train จาก label ชั่งเดี่ยว เพื่อทำนายน้ำหนักแต่ละตัว แล้วรวมเป็นน้ำหนักทั้งกลุ่มเพื่อ cross-check กับตราชั่งได้

## 10. การแบ่งข้อมูลและการวัดผล

- แบ่ง train/validation/test ตามวันเก็บข้อมูลหรือ `batch_id` ห้ามสุ่มเฟรมจากการชั่งตัวเดิมข้ามชุด
- ประเมิน `MAE (g)`, `RMSE (g)`, `MAPE (%)` และค่า P95 absolute error
- รายงานผลแยกตามช่วงน้ำหนัก, batch, กล้อง และสถานะ quality gate
- เริ่มต้นควรมีอย่างน้อย 500–1,000 ตัวอย่างที่มี label รายตัว และครอบคลุมน้ำหนักต่ำถึงสูงจริง

## 11. ลำดับการพัฒนาที่แนะนำ

1. ปรับ capture metadata ให้บันทึก `actual_weight_g` รายตัวและ quality flags
2. สร้างตาราง feature จาก `per_chicken_records` และ derived features ตามเอกสารนี้
3. ตรวจ calibration และความสมเหตุสมผลของหน่วย mm ก่อน train
4. สร้าง baseline XGBoost ด้วยชุด feature เริ่มต้น
5. วิเคราะห์ feature importance และ error ตาม batch/น้ำหนัก
6. ปรับ quality gates และ feature engineering แล้ว train/evaluate ซ้ำ

