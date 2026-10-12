# Runbook: ดึงภาพ Single-bird สำหรับช่วงวันที่ 2026-10-04 ถึง 2026-10-06

เอกสารนี้อธิบายขั้นตอนตั้งแต่ export metadata จาก PostgreSQL จนได้ภาพ
single-bird candidate อยู่ใน Windows สำหรับตรวจสอบด้วยคนและใช้เป็นข้อมูลฝึกในขั้นถัดไป

## เริ่มแบบเร็ว: สคริปต์ใช้ซ้ำได้สำหรับทุก batch

เมื่อทำข้อ 1--2 เสร็จแล้ว (มี PostgreSQL metadata export และสร้าง candidate manifest แล้ว)
ให้ใช้ `download_single_bird_candidates.ps1` ซึ่งรับ path ของ manifest และวันที่เป็นพารามิเตอร์
จึงใช้กับช่วงข้อมูลถัดไปได้โดยไม่ต้องแก้โค้ดสคริปต์ สคริปต์ทำ MinIO → Linux `qi67` → Windows
ครบในคำสั่งเดียว และดึงเฉพาะ object key ใน manifest เท่านั้น

> หมายเหตุเรื่องภาพสีเขียว: แต่ละ session ใน bucket นี้เก็บ original JPEG และ
> inference-overlay JPEG เป็นคู่กัน Generator จะเลือก media object ที่มี `created_at` เร็วที่สุด
> ของ session (original JPEG) เท่านั้น จึงไม่ควรมี mask/เส้นขอบสีเขียวหรือ ROI สีแดงในภาพที่ดึง

ภาพที่ดึงแล้วอยู่ที่:

```text
ml_weight_prediction/data/raw/single_bird_candidates/YYYY-MM-DD/
```

## วิธีใช้สคริปต์กับ batch ใหม่

หลังสร้าง candidate manifest แล้ว ให้ใช้ `download_single_bird_candidates.ps1` แทนการ
คัดลอกฟังก์ชัน PowerShell สองตัวจากเอกสารนี้ สคริปต์ทำทั้ง MinIO → Linux `qi67` → Windows
และดาวน์โหลดเฉพาะ `object_key` ใน manifest:

```powershell
$root = 'E:\FarmIQ_V02\cloud-layer\cloud-ml-model-service'
$range = '20261004_20261007'

& "$root\ml_weight_prediction\scripts\download_single_bird_candidates.ps1" `
  -Manifest "$root\ml_weight_prediction\data\processed\single_bird_export_candidates_$range.csv" `
  -Dates '2026-10-04', '2026-10-05', '2026-10-06'
```

สคริปต์จะถามรหัสผ่าน SSH ตามปกติ และข้ามวันที่ไม่มี candidate โดยอัตโนมัติ

สำหรับช่วงวันอื่น ให้เปลี่ยนเพียงสองส่วนนี้:

1. `$range` ต้องตรงกับชื่อ manifest ที่สร้างในขั้นที่ 2 เช่น `20261007_20261010`
   หมายถึงข้อมูลวันที่ 7--9 ต.ค. และสิ้นสุดก่อน 10 ต.ค.
2. `-Dates` ต้องระบุทุกวันที่ต้องการดาวน์โหลด เช่น
   `-Dates '2026-10-07', '2026-10-08', '2026-10-09'`

ไม่ต้องใช้ `download_single_bird_20260930_20261003.ps1` สำหรับ batch ใหม่ เพราะสคริปต์นั้น
เป็นไฟล์เก่าที่ล็อก manifest และวันที่ของช่วง 30 ก.ย.--3 ต.ค. ไว้แล้ว

> ข้อสำคัญ: candidate ไม่ใช่ training label ที่ยืนยันแล้ว แม้ detector จะรายงานหนึ่งตัว
> (`detection_count=1`) ก็ยังต้องตรวจด้วยสายตาว่ามีไก่เพียงตัวเดียวบนแท่นชั่งจริง
> ก่อนตั้ง `use_for_training=true`

## ขอบเขตและชื่อไฟล์

- วันที่ภาพ: `2026-10-04` ถึง `2026-10-06` (รวมวันที่ 6)
- พาธ object ใน MinIO: `.../images/2026/10/04/` ถึง `.../images/2026/10/06/`
- ชื่อ export folder: `20261004_20261007`
- ช่วงเวลา SQL: ตั้งต้นรวม (`>=`) `2026-10-04 00:00:00` และสิ้นสุดไม่รวม (`<`)
  `2026-10-07 00:00:00`

ให้ใช้ timezone เดียวกับนิยาม “วัน” ของฟาร์ม/ระบบ export เดิม และใช้ช่วงเวลาเดียวกันกับทั้ง
สี่ไฟล์ ไม่ควรใช้ `BETWEEN` เพราะทำให้ข้อมูลที่ขอบวันซ้ำกับ export รอบถัดไปได้

## 1. Export metadata จาก PostgreSQL

PostgreSQL อยู่บน Linux host `qi67@100.69.28.16` และทำงานใน Docker ดังนั้นต้อง export
CSV บน `qi67` ก่อน แล้วจึงใช้ `scp` นำไฟล์กลับมายัง Windows เพื่อสร้าง candidate manifest
ในขั้นถัดไป

### 1.1 สร้างโฟลเดอร์ export และเข้าเครื่อง `qi67`

บน Windows PowerShell กำหนดชื่อช่วงข้อมูลและโฟลเดอร์ปลายทางใน Windows:

```powershell
$range = '20261004_20261007'
$root = 'E:\FarmIQ_V02\cloud-layer\cloud-ml-model-service'
$metadataBase = "$root\ml_weight_prediction\data\raw\farm_export_metadata"
New-Item -ItemType Directory -Force -Path $metadataBase | Out-Null

ssh qi67@100.69.28.16
```

เมื่ออยู่ที่ Linux prompt ให้ตรวจชื่อ PostgreSQL container ก่อน (อย่าคาดเดาชื่อ container):

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}' | grep -i postgres
```

สร้างโฟลเดอร์ export บน Linux:

```bash
export RANGE=20261004_20261007
export EXPORT_DIR="/home/qi67/FarmIQ_Filter/farm_export_metadata/$RANGE"
mkdir -p "$EXPORT_DIR"
```

Export ให้ได้ไฟล์ CSV ต่อไปนี้ใน `$EXPORT_DIR` โดยคง header และทุกคอลัมน์ต้นฉบับไว้:

```text
session_capture_metadata_20261004_20261007.csv
media_objects_20261004_20261007.csv
weight_sessions_20261004_20261007.csv
inference_results_20261004_20261007.csv
```

> **คำสั่งด้านล่างเป็น SQL ไม่ใช่ Bash:** ห้ามพิมพ์เงื่อนไข `>= ...` หรือ `< ...`
> ที่ Linux prompt โดยตรง ให้เปิด `psql` ของ PostgreSQL container (หรือใช้เครื่องมือ export
> เดิมของระบบ) ก่อน แล้วจึงรัน SQL ใน prompt `psql` เท่านั้น

ตัวอย่างการเปิด `psql` โดยใช้ user/database ที่ตั้งอยู่ใน container:

```bash
docker exec -it edge-layer-postgres-1 sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

ถ้า container ชื่อไม่ใช่ `edge-layer-postgres-1` ให้ใช้ชื่อที่ตรวจพบจาก `docker ps`
แทน หลังเข้า `psql` แล้ว ใช้ `\dt` เพื่อตรวจตาราง และ `\q` เพื่อออก

ใช้เครื่องมือ export PostgreSQL ของระบบเดิม หรือ `psql` กับ query ที่ทีมใช้งานอยู่
โดยยึดหลักดังนี้:

1. เลือก `session_capture_metadata` ด้วยเวลา capture/occurred ในช่วงวันที่กำหนด
2. เลือก `media_objects`, `weight_sessions`, และ `inference_results` จาก `session_id`
   ของ capture ที่เลือก เพื่อไม่ให้ metadata หลุด join
3. จำกัด tenant/farm/barn/device เดียวกับชุดข้อมูลที่จะใช้ (ตัวอย่างเดิมคือ
   `t-001/f-001/b-001/wv-001`)

คำสั่งด้านล่างผ่านการใช้งานกับฐานข้อมูลจริงเมื่อวันที่ 2026-10-07 แล้ว
(`public` schema, container `edge-layer-postgres-1`) ให้พิมพ์แต่ละบรรทัดใน prompt `psql`
และรอผลลัพธ์รูปแบบ `COPY <จำนวนแถว>` ก่อนพิมพ์บรรทัดต่อไป:

```sql
\copy (SELECT c.* FROM public.session_capture_metadata AS c WHERE c.tenant_id = 't-001' AND c.occurred_at >= TIMESTAMPTZ '2026-10-04 00:00:00+07' AND c.occurred_at < TIMESTAMPTZ '2026-10-07 00:00:00+07' AND EXISTS (SELECT 1 FROM public.weight_sessions AS w WHERE w.session_id = c.session_id AND w.tenant_id = 't-001' AND w.farm_id = 'f-001' AND w.barn_id = 'b-001' AND w.device_id = 'wv-001')) TO '/tmp/session_capture_metadata_20261004_20261007.csv' WITH (FORMAT csv, HEADER true);

\copy (SELECT m.* FROM public.media_objects AS m WHERE m.tenant_id = 't-001' AND m.farm_id = 'f-001' AND m.barn_id = 'b-001' AND m.device_id = 'wv-001' AND m.session_id IN (SELECT c.session_id FROM public.session_capture_metadata AS c WHERE c.tenant_id = 't-001' AND c.occurred_at >= TIMESTAMPTZ '2026-10-04 00:00:00+07' AND c.occurred_at < TIMESTAMPTZ '2026-10-07 00:00:00+07')) TO '/tmp/media_objects_20261004_20261007.csv' WITH (FORMAT csv, HEADER true);

\copy (SELECT w.* FROM public.weight_sessions AS w WHERE w.tenant_id = 't-001' AND w.farm_id = 'f-001' AND w.barn_id = 'b-001' AND w.device_id = 'wv-001' AND w.session_id IN (SELECT c.session_id FROM public.session_capture_metadata AS c WHERE c.tenant_id = 't-001' AND c.occurred_at >= TIMESTAMPTZ '2026-10-04 00:00:00+07' AND c.occurred_at < TIMESTAMPTZ '2026-10-07 00:00:00+07')) TO '/tmp/weight_sessions_20261004_20261007.csv' WITH (FORMAT csv, HEADER true);

\copy (SELECT i.* FROM public.inference_results AS i WHERE i.tenant_id = 't-001' AND i.farm_id = 'f-001' AND i.barn_id = 'b-001' AND i.device_id = 'wv-001' AND i.session_id IN (SELECT c.session_id FROM public.session_capture_metadata AS c WHERE c.tenant_id = 't-001' AND c.occurred_at >= TIMESTAMPTZ '2026-10-04 00:00:00+07' AND c.occurred_at < TIMESTAMPTZ '2026-10-07 00:00:00+07')) TO '/tmp/inference_results_20261004_20261007.csv' WITH (FORMAT csv, HEADER true);
```

ออกจาก `psql` ด้วย `\q` แล้วคัดลอก CSV ที่ถูกสร้างใน container ไปยัง `$EXPORT_DIR`
บน Linux host:

```bash
docker cp edge-layer-postgres-1:/tmp/session_capture_metadata_20261004_20261007.csv "$EXPORT_DIR/"
docker cp edge-layer-postgres-1:/tmp/media_objects_20261004_20261007.csv "$EXPORT_DIR/"
docker cp edge-layer-postgres-1:/tmp/weight_sessions_20261004_20261007.csv "$EXPORT_DIR/"
docker cp edge-layer-postgres-1:/tmp/inference_results_20261004_20261007.csv "$EXPORT_DIR/"
```

ขั้นต่ำที่ candidate generator ต้องใช้คือ:

| CSV | คอลัมน์ที่จำเป็น |
| --- | --- |
| `session_capture_metadata` | `session_id`, `raw_metadata`, และเวลา capture |
| `media_objects` | `id`, `session_id`, `bucket`, `object_key`, `captured_at` |
| `weight_sessions` | `session_id`, `status` |

`inference_results` ไม่ได้ใช้สร้าง single-bird manifest ในรอบนี้ แต่ต้องเก็บไว้คู่กับ export
เพื่อ audit และการทดลองภายหลัง

ตรวจไฟล์บน Linux ก่อน:

```bash
ls -lh "$EXPORT_DIR"
exit
```

### 1.2 นำ CSV กลับมายัง Windows

หลัง `exit` กลับมาที่ Windows PowerShell ให้ดึงโฟลเดอร์ช่วงข้อมูลกลับมา:

```powershell
scp -r "qi67@100.69.28.16:/home/qi67/FarmIQ_Filter/farm_export_metadata/$range" $metadataBase

$metadataDir = Join-Path $metadataBase $range
Get-ChildItem $metadataDir -File | Select-Object Name, Length
```

หากไฟล์ชื่อหรือ `$range` ไม่ตรงกับที่ส่งให้ candidate generator ขั้นที่ 2 ให้แก้ให้ตรงกัน
ก่อนดำเนินการต่อ

## 2. สร้าง candidate manifest

จาก root ของ service (`cloud-ml-model-service`) ให้รัน:

```powershell
$root = 'E:\FarmIQ_V02\cloud-layer\cloud-ml-model-service'
$python = 'python'

& $python "$root\ml_weight_prediction\scripts\export_single_bird_candidates.py" `
  --captures "$metadataDir\session_capture_metadata_20261004_20261007.csv" `
  --media "$metadataDir\media_objects_20261004_20261007.csv" `
  --weight-sessions "$metadataDir\weight_sessions_20261004_20261007.csv" `
  --output "$root\ml_weight_prediction\data\processed\single_bird_export_candidates_20261004_20261007.csv" `
  --summary-output "$root\ml_weight_prediction\data\processed\single_bird_export_candidates_20261004_20261007.summary.json"
```

ตรวจ summary โดยเฉพาะ `download_candidates` และ `rejected`:

```powershell
Get-Content "$root\ml_weight_prediction\data\processed\single_bird_export_candidates_20261004_20261007.summary.json"
```

ถ้า `download_candidates` เป็น `0` ให้หยุดตรวจ metadata/เงื่อนไขก่อน ไม่ต้องดึงรูปจาก MinIO

## 3. รายละเอียดกลไกการดึงภาพด้วยตนเอง (อ้างอิง)

ปกติไม่ต้องคัดลอกฟังก์ชันในหัวข้อนี้ลง PowerShell เพราะให้ใช้
`download_single_bird_candidates.ps1` ตามคำสั่งด้านบน หัวข้อนี้เก็บไว้เพื่ออธิบายกลไก
และใช้แก้ปัญหาเฉพาะกรณีเท่านั้น

```powershell
$manifest = "$root\ml_weight_prediction\data\processed\single_bird_export_candidates_20261004_20261007.csv"
$destination = "$root\ml_weight_prediction\data\raw\single_bird_candidates"
$downloader = "$root\ml_weight_prediction\scripts\download_minio_objects.py"

$remote = 'qi67@100.69.28.16'
$remoteRoot = '/home/qi67/FarmIQ_Filter/clean'

if (-not (Test-Path $manifest)) { throw "ไม่พบ manifest: $manifest" }
if (-not (Test-Path $downloader)) { throw "ไม่พบ downloader: $downloader" }
```

นิยามฟังก์ชันแรกเพื่อดึงเฉพาะ object ที่อยู่ใน manifest จาก MinIO ไปยังเครื่อง SSH:

```powershell
function Sync-FarmIQSingleBirdDayToRemote([string]$dateDir) {
  $datePath = $dateDir.Replace('-', '/')
  $keysFile = "$env:TEMP\farmiq_object_keys_$dateDir.txt"
  $remoteKeys = "/tmp/farmiq_object_keys_$dateDir.txt"
  $remoteScript = '/tmp/download_minio_objects.py'

  $keys = @(
    Import-Csv $manifest |
      Where-Object { $_.object_key -like "*/images/$datePath/*" } |
      Select-Object -ExpandProperty object_key -Unique
  )
  if ($keys.Count -eq 0) {
    Write-Warning "ไม่มี candidate สำหรับ $dateDir"
    return
  }

  [IO.File]::WriteAllLines($keysFile, $keys, (New-Object System.Text.UTF8Encoding($false)))
  scp $downloader "${remote}:$remoteScript"
  if ($LASTEXITCODE -ne 0) { throw "ส่ง downloader ไป SSH ไม่สำเร็จ: $dateDir" }
  scp $keysFile "${remote}:$remoteKeys"
  if ($LASTEXITCODE -ne 0) { throw "ส่ง object key list ไป SSH ไม่สำเร็จ: $dateDir" }

  ssh $remote "python3 '$remoteScript' --keys-file '$remoteKeys' --destination '$remoteRoot/$dateDir'"
  if ($LASTEXITCODE -ne 0) { throw "ดึงรูปจาก MinIO ไม่สำเร็จ: $dateDir" }
}
```

นิยามฟังก์ชันที่สองเพื่อรวมเฉพาะชื่อไฟล์ใน manifest เป็น archive แล้วดึงกลับ Windows:

```powershell
function Get-FarmIQSingleBirdDay([string]$dateDir) {
  $datePath = $dateDir.Replace('-', '/')
  $list = "$env:TEMP\farmiq_single_bird_$dateDir.txt"
  $remoteList = "/tmp/farmiq_single_bird_$dateDir.txt"
  $remoteArchive = "/tmp/farmiq_single_bird_$dateDir.tar"
  $localArchive = "$env:TEMP\farmiq_single_bird_$dateDir.tar"
  $outputDay = Join-Path $destination $dateDir

  $names = @(
    Import-Csv $manifest |
      Where-Object { $_.object_key -like "*/images/$datePath/*" } |
      ForEach-Object { [IO.Path]::GetFileName($_.object_key) } |
      Sort-Object -Unique
  )
  if ($names.Count -eq 0) {
    Write-Warning "ไม่พบรายการรูปสำหรับ $dateDir"
    return
  }

  [IO.File]::WriteAllText($list, (($names -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
  New-Item -ItemType Directory -Force -Path $outputDay | Out-Null

  scp $list "${remote}:$remoteList"
  if ($LASTEXITCODE -ne 0) { throw "ส่งรายการไป SSH ไม่สำเร็จ: $dateDir" }
  ssh $remote "tar --ignore-failed-read -C '$remoteRoot/$dateDir' -cf '$remoteArchive' -T '$remoteList'"
  if ($LASTEXITCODE -ne 0) { throw "สร้าง archive บน SSH ไม่สำเร็จ: $dateDir" }
  scp "${remote}:$remoteArchive" $localArchive
  if ($LASTEXITCODE -ne 0) { throw "ดาวน์โหลด archive ไม่สำเร็จ: $dateDir" }
  tar -xf $localArchive -C $outputDay
  if ($LASTEXITCODE -ne 0) { throw "แตก archive ไม่สำเร็จ: $dateDir" }

  $count = (Get-ChildItem $outputDay -File -Filter '*.jpg').Count
  Write-Host "เสร็จ: $dateDir — $count รูป → $outputDay"
}
```

## 4. ดึงภาพจาก MinIO ไปยังเครื่อง Linux `qi67`

```powershell
Sync-FarmIQSingleBirdDayToRemote '2026-10-04'
Sync-FarmIQSingleBirdDayToRemote '2026-10-05'
Sync-FarmIQSingleBirdDayToRemote '2026-10-06'
```

ขั้นนี้บันทึกเฉพาะ candidate ลง Linux host `qi67@100.69.28.16` ที่:

```text
/home/qi67/FarmIQ_Filter/clean/YYYY-MM-DD/
```

ขั้นนี้ยังไม่มีไฟล์ภาพอยู่บน Windows

## 5. ดึงภาพจาก Linux `qi67` กลับมายัง Windows

เมื่อ `Sync-FarmIQSingleBirdDayToRemote` สำเร็จ ให้รัน:

```powershell
Get-FarmIQSingleBirdDay '2026-10-04'
Get-FarmIQSingleBirdDay '2026-10-05'
Get-FarmIQSingleBirdDay '2026-10-06'
```

`Get-FarmIQSingleBirdDay` จะอ่านชื่อ JPG จาก manifest, สร้าง tar บน Linux,
ใช้ `scp` ดาวน์โหลด tar มาที่ `%TEMP%` ของ Windows และแตกไฟล์ลงปลายทางด้านล่าง

ผลลัพธ์อยู่ที่:

```text
ml_weight_prediction/data/raw/single_bird_candidates/YYYY-MM-DD/
```

ตรวจจำนวนและชื่อไฟล์:

```powershell
'2026-10-04', '2026-10-05', '2026-10-06' | ForEach-Object {
  $outputDay = Join-Path $destination $_
  $count = (Get-ChildItem $outputDay -File -Filter '*.jpg' -ErrorAction SilentlyContinue).Count
  Write-Host "$_ : $count รูป"
}
```

ระหว่าง `Sync...` และ `Get...` จะมีการถาม SSH password หลายครั้งตาม `scp`/`ssh` ที่เรียกใช้

## 6. ตรวจด้วยสายตาและจัดทำ training labels

สำหรับแต่ละ candidate ให้ยืนยันอย่างน้อย:

1. มีไก่เพียงหนึ่งตัวบนแท่นชั่ง/ROI จริง
2. ภาพและ session จับคู่กับน้ำหนักที่แสดงบนตาชั่งได้
3. บันทึก `visual_review_status`, `visually_verified_single_bird`, และ
   `use_for_training` ในไฟล์ review ที่แยกจาก manifest ต้นฉบับ

ห้ามใช้ candidate ที่ยังไม่ review เป็น label สำหรับฝึก individual-weight model

## การแก้ปัญหา

### `Is a directory: ...jpg.part -> ...jpg`

เคยใช้ `docker cp` กับ MinIO มาก่อน ทำให้มี directory ภายในที่ใช้ชื่อเหมือนไฟล์ JPG
ให้ลบเฉพาะโฟลเดอร์วันนั้นบนเครื่อง SSH แล้ว sync ใหม่:

```powershell
ssh $remote "rm -rf '$remoteRoot/2026-10-04' && mkdir -p '$remoteRoot/2026-10-04'"
Sync-FarmIQSingleBirdDayToRemote '2026-10-04'
```

### ไม่พบ candidate

เปิด `single_bird_export_candidates_20261004_20261007.summary.json` แล้วตรวจ
`rejected` เพื่อดูว่า candidate ถูกตัดออกเพราะ scale ไม่ stable, detector ไม่ใช่หนึ่งตัว,
หรือไม่มี media object

### ห้ามใช้ `docker cp` หรือ MinIO Console เพื่อ batch download

MinIO เก็บข้อมูลภายในเป็น object-storage format จึงไม่สามารถคัดลอก directory จาก
container แล้วคาดหวังว่าจะได้ JPG ที่ใช้งานได้ ใช้ `Sync-FarmIQSingleBirdDayToRemote`
ซึ่งเรียก `download_minio_objects.py` ผ่าน MinIO S3 API เท่านั้น
