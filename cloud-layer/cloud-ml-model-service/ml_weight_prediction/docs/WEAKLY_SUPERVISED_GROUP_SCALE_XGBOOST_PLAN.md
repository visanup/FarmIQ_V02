# FarmIQ: แผนพัฒนา XGBoost สำหรับหลายไก่ใน ROI และน้ำหนักรวมจากตราชั่ง

## 1. บริบทและขอบเขต

ภาพหนึ่งภาพมองจากด้านบนไปยังแท่นชั่งซึ่งถูกกำหนดด้วย ROI สีแดง ระบบ
YOLO instance segmentation แยกไก่แต่ละตัวที่อยู่บนแท่นเป็น mask แล้ว stereo
คำนวณมิติทางกายภาพให้แต่ละ mask ตราชั่งให้ค่าเดียว คือ `group_total_weight_g`
ของไก่ทุกตัวที่อยู่บนแท่น ณ เวลาที่ตราชั่งนิ่ง

เอกสารนี้กำหนดแผนสำหรับการ **จัดสรรน้ำหนักรวมให้ไก่แต่ละตัวในภาพ**
(group-constrained allocation) โดยใช้ XGBoost แบบ weak supervision แยกจาก
โมเดลทำนายน้ำหนักรายตัวที่มี label ชั่งจริง

| เรื่อง | Weakly supervised allocation | Individual-weight model |
|---|---|---|
| Label ที่มี | น้ำหนักรวมของภาพ | น้ำหนักจริงของไก่แต่ละตัว |
| Output | สัดส่วน/น้ำหนักรายตัวที่รวมกันเท่ากับตราชั่ง | น้ำหนักอิสระรายตัว |
| สถานะความเชื่อมั่น | ต้องระบุว่าเป็น weakly supervised | วัด MAE รายตัวได้ |
| ใช้ data ปัจจุบันได้ | ได้ หลังผ่าน quality gate | ยังไม่ได้จนกว่าจะมี individual labels |

ห้ามเรียก output ของ phase weak supervision ว่า `actual_weight_g` หรือ
รายงานว่าเป็นความแม่นยำรายตัว หากยังไม่มี reference scale ที่ชั่งรายตัว

## 2. สิ่งที่เห็นจากภาพและกติกา ROI

- ใช้เฉพาะ mask ที่สัมพันธ์กับไก่บนแท่นชั่ง ไม่ใช่ไก่ที่อยู่นอก ROI
- ต้องเก็บ `is_inside_roi`, `is_mask_clipped`, และ `overlap_ratio_with_roi`
  ต่อ detection
- mask ที่แตะหรือข้ามขอบ ROI มีโอกาสเป็นไก่ที่ขึ้น/ลงแท่นหรือถูกตัดภาพ
  จึงไม่ใช้สร้างน้ำหนักรายตัวใน v1; เก็บเป็น audit event
- `chicken_count` ต้องเท่ากับจำนวน mask ที่ผ่าน gate ไม่ใช่จำนวน detection
  ดิบทั้งหมด
- สำหรับ weak-label train ต้อง reject ทั้ง session หากมี mask ใน ROI แม้แต่ตัว
  เดียวไม่ผ่าน gate เพราะน้ำหนักรวมของตราชั่งยังรวมมวลของตัวที่ถูกตัดออกอยู่
- `group_total_weight_g` ต้องเป็นค่าน้ำหนักหลัง tare, มาจาก scale เดียวกัน
  และอ่านเฉพาะเมื่อ `weight_stable=true`

ตัวอย่างภาพ annotation ที่มี mask หลายตัวใน ROI เป็น input ที่ถูกต้องสำหรับ
flow นี้ แต่ต้องตรวจ mask ที่ติดขอบ ROI ก่อนนับเข้ากลุ่ม

## 3. นิยามข้อมูลและ schema

สร้างสองตารางแยกกัน: ตาราง `session` หนึ่งแถวต่อการชั่ง และตาราง
`bird_detection` หนึ่งแถวต่อ mask ที่ผ่าน ROI matching

### 3.1 `weighing_session`

```text
session_id                         # unique ID
captured_at_utc
camera_id
farm_id / barn_id
batch_id
age_days                           # required for breed-standard checks
breed = Arbor_Acres_Plus
sex = male
scale_id
scale_calibration_version
scale_tare_verified
weight_stable
group_total_weight_g
raw_detection_count
eligible_chicken_count
image_width_px
image_height_px
roi_xyxy
```

### 3.2 `bird_detection`

```text
session_id
detection_index
track_id                           # optional; required if multiple frames are linked
is_inside_roi
overlap_ratio_with_roi
is_mask_clipped
area_mm2
length_mm
width_mm
height_mm
depth_mm
confidence
bbox_xyxy
mask_area_px
centroid_x_norm
centroid_y_norm
quality_pass
quality_reasons
```

Derived training fields:

```text
pseudo_weight_g = group_total_weight_g / eligible_chicken_count
session_sample_weight = 1 / eligible_chicken_count
standard_male_weight_g             # lookup by age_days; reference only
volume_proxy_area_height_mm3 = area_mm2 * height_mm
volume_proxy_lwh_mm3 = length_mm * width_mm * height_mm
length_width_ratio = length_mm / width_mm
```

`pseudo_weight_g` ต้องเก็บเป็นชื่อเฉพาะนี้ ห้ามเปลี่ยนชื่อเป็น
`actual_weight_g` แม้เป็นตัวเลขกรัม

## 4. Quality gates

### 4.1 Gate ระดับ session

รับ session เมื่อครบทุกข้อ:

- `weight_stable=true`
- ค่า `group_total_weight_g` เป็นบวกและหลัง tare
- scale ID และ calibration version มีค่า
- มี `eligible_chicken_count >= 1`
- มีเวลา capture และ camera ID
- มี `age_days`, breed และ sex สำหรับ Arbor Acres male scope
- ไม่มี track/detection ซ้ำใน session

### 4.2 Gate ระดับไก่

รับ detection เมื่อครบทุกข้อ:

- confidence ตั้งต้น `>= 0.80`
- mask อยู่ใน ROI ตามเกณฑ์ overlap ที่ทีม vision อนุมัติ
- `is_mask_clipped=false`
- area, length, width, height และ depth เป็น finite และมากกว่า 0
- bbox, mask area และ image dimensions ใช้คำนวณ derived features ได้
- ผ่าน geometry range ที่ตั้งจากชุด train เท่านั้น ไม่ใช้ threshold ที่เดาขึ้น

เก็บทุกแถวที่ถูกปฏิเสธใน audit โดยมี `quality_reasons` หลายค่าได้ ห้ามลบ
ทิ้งก่อนตรวจสอบ root cause

## 5. กลยุทธ์โมเดล

### Phase A — Baseline ที่อธิบายได้

เปรียบเทียบอย่างน้อยสอง baseline ต่อ session:

1. **Equal split:** `w_i = group_total_weight_g / N`
2. **Volume-proxy split:** `w_i = group_total_weight_g * v_i / sum(v_j)` โดย
   `v_i` เป็น volume proxy ที่ผ่าน quality gate

ทั้งสองแบบเป็น allocation ไม่ใช่น้ำหนักยืนยันรายตัว แต่มีประโยชน์สำหรับ
ตรวจ pipeline และเป็น benchmark ของ XGBoost

### Phase B — XGBoost pseudo-label model

สร้างหนึ่งแถวต่อไก่ด้วย feature ด้านล่างและ target `pseudo_weight_g`:

```text
area_mm2, length_mm, width_mm, height_mm, depth_mm, confidence,
volume_proxy_area_height_mm3, volume_proxy_lwh_mm3, length_width_ratio,
bbox_area_px, bbox_aspect_ratio, mask_fill_ratio,
centroid_x_norm, centroid_y_norm, is_height_outlier
```

ส่ง `session_sample_weight = 1/N` ให้ XGBoost เพื่อให้แต่ละ session มี
อิทธิพลรวมเท่ากัน ไม่เช่นนั้น session ที่มีไก่มากจะถูกนับซ้ำมากกว่า

เมื่อ inference มีน้ำหนักรวมจากตราชั่ง ให้แปลง prediction ดิบของแต่ละตัว
เป็นน้ำหนักที่อนุรักษ์ยอดรวม:

```text
q_i = max(xgb_prediction_i, epsilon)
allocated_weight_g_i = group_total_weight_g * q_i / sum(q_j)
```

ดังนั้น `sum(allocated_weight_g_i) = group_total_weight_g` ภายใน tolerance
ของ floating point เสมอ

**ข้อจำกัด:** pseudo label ทำให้ไก่ทุกตัวใน session เดียวกันได้ target เท่ากัน
และ group total ให้เพียงหนึ่งสมการสำหรับน้ำหนักหลายตัว จึงไม่สามารถระบุว่า
allocation รายตัวถูกต้องจากข้อมูลนี้เพียงอย่างเดียว

### Phase C — Group-loss experiment (หลัง Phase B)

พิจารณา custom grouped objective ที่ลด error ของ
`sum(prediction_i) - group_total_weight_g` ตาม session ได้ แต่ XGBoost ใช้
Hessian แบบรายแถว จึงเป็นเพียง approximation สำหรับ loss ที่เชื่อมหลายแถว
และยังมีปัญหา identifiability เหมือนเดิม ต้องมี individual anchor labels
ก่อนใช้ผลเพื่อ promotion

### Phase D — Individual-calibrated model

เก็บชุด calibration ที่ชั่งไก่เดี่ยวหรือมี track-to-scale linkage ที่ตรวจสอบ
ได้ แล้วใช้ `actual_weight_g` เป็น target จริง:

- ใช้ข้อมูลนี้เป็น validation/test ที่ล็อกไว้
- วัด MAE, RMSE, P95 absolute error และ bias รายตัว
- ใช้ Phase B model เป็น baseline ไม่ใช่ ground truth
- ปรับ model package เป็น `INDIVIDUAL_CALIBRATED` เฉพาะเมื่อผ่าน release gate

## 6. Breed standard: Arbor Acres Plus male

ไฟล์ `Arbor_Acres_Plus_Broiler_Performance.xlsx` เป็น standard growth
reference ของ Arbor Acres Plus male ใช้ lookup `standard_male_weight_g` จาก
`age_days` เพื่อ:

- ตรวจ plausibility ของ group mean (`group_total_weight_g / N`)
- สร้าง drift/quality alert เมื่อค่าห่างจาก standard เกินขอบเขตที่ฟาร์มอนุมัติ
- stratify รายงานตามอายุ

ห้ามใช้ standard body weight เป็น target แทน scale reading หรือ individual
label เพราะเป็นค่าเฉลี่ยเป้าหมาย ไม่ใช่น้ำหนักที่วัดจริงของไก่ในภาพ

## 7. Train / validation / test

- แยกด้วย `batch_id` หรือ collection day; ห้ามสุ่ม detection จาก session เดียว
  ไปอยู่คนละ split
- หากเป็นวิดีโอหรือหลาย frame ต่อกลุ่มเดิม ให้ทุก `track_id` และทุก frame
  ของกลุ่มนั้นอยู่ split เดียวกัน
- ใช้กลุ่มวัน/batch ล่าสุดเป็น test ที่ล็อกไว้; validation ต้องมาก่อน test
  ตามเวลา
- อย่างน้อย 5 independent days/batches เพื่อเริ่มทดลอง split; 221 session ใน
  วันเดียวไม่แสดงการ generalize ข้ามวันหรือข้าม batch
- report จำนวน session, จำนวนไก่, distribution ของ `N`, อายุ, น้ำหนักรวม,
  camera และ quality rejection ในทุก split

## 8. การประเมินผลที่ซื่อสัตย์

### ทำได้จาก group labels ปัจจุบัน

- session coverage, stable-scale rate, ROI/mask rejection rate
- error ของ `sum(raw_q_i)` ต่อ group total **ก่อน normalization**
- error ของ group-level aggregate baseline/XGBoost ต่อ scale total
- เปรียบเทียบ allocation distribution กับ equal split และ volume-proxy split
- difference ระหว่าง group mean และ Arbor male standard ตาม `age_days`

### ทำไม่ได้จนกว่าจะมี individual labels

- MAE/RMSE/P95 ของ `allocated_weight_g_i` ต่อไก่
- rank accuracy ว่าตัวที่หนักสุดในภาพถูกต้องหรือไม่
- claim ว่า XGBoost ดีกว่า volume proxy ในระดับไก่

ห้ามวัด error ของ `sum(allocated_weight_g_i)` หลัง normalization เพราะยอดรวม
ถูกบังคับให้เท่าตราชั่งตามสูตรอยู่แล้ว ผลเป็นศูนย์ไม่ได้แปลว่า allocation ถูกต้อง

## 9. Edge inference contract

Input ต่อ session:

```json
{
  "session_id": "...",
  "group_total_weight_g": 1350,
  "weight_stable": true,
  "age_days": 14,
  "breed": "Arbor_Acres_Plus",
  "sex": "male",
  "detections": [{"detection_index": 0, "area_mm2": 0, "...": "..."}]
}
```

Output ต่อ detection:

```json
{
  "session_id": "...",
  "detection_index": 0,
  "allocated_weight_g": 0,
  "prediction_status": "WEAK_ALLOCATION",
  "model_version": "...",
  "quality_reasons": []
}
```

Session ที่ scale ไม่ stable, ไม่มี detection ผ่าน gate, หรือน้ำหนักรวมผิดรูปแบบ
ต้องคืน `REJECTED_QUALITY` และไม่ส่ง allocation เงียบ ๆ

## 10. Shadow, promotion, rollback

### Shadow

1. รัน allocation โดยไม่ส่งผลไปตัดสินใจหน้างาน
2. log raw feature, `raw_q_i`, allocated weight, group total, quality status,
   model version, latency, age/batch/camera และ standard comparison
3. ตรวจ session completeness และ raw group-total error ก่อน normalization
4. สุ่มชั่งไก่เดี่ยวเพื่อสร้าง calibration set ระหว่าง shadow

### เงื่อนไข promotion แบบ weak allocation

- ตราชั่งนิ่งและ data contract ผ่านในอัตราที่ทีมปฏิบัติการอนุมัติ
- ไม่มี silent fallback เมื่อ quality gate fail
- allocation รวมเท่ากับ scale total และมี audit log ครบ
- ผู้ใช้ปลายทางยอมรับสถานะ `WEAK_ALLOCATION` และไม่ใช้เป็นการชั่งรับรองรายตัว

### Rollback

ย้อนกลับเป็นแสดงเฉพาะ `group_total_weight_g` หากพบ scale/ROI mismatch,
geometry invalid เพิ่มขึ้น, schema/calibration เปลี่ยน, หรือ logging หาย
ห้ามใช้ aggregate-total equality หลัง normalization เป็นสัญญาณว่าโมเดลปลอดภัย

## 11. Backlog ตามลำดับ

1. เพิ่ม session/detection schema และ ROI containment flags ที่ source
2. เพิ่ม flock placement date หรือ `age_days`, breed, sex, scale calibration
3. สร้าง labelled weak dataset, audit table และ baseline allocation สองแบบ
4. Train XGBoost pseudo-label พร้อม session weights และ time/group split
5. สร้าง edge group-inference wrapper ที่ normalize ภายใน session
6. เปิด shadow และเก็บ individual calibration labels
7. ประเมิน Phase D ก่อน claim individual-weight accuracy หรือใช้งานเชิงธุรกิจ
