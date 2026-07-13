# Weight Vision Train Model (YOLO26)

## Overview
Train a YOLO26 model from the dataset in:

`Chicken Segmentation.yolo26`

This trainer supports both Roboflow export layouts:
- **flat export**: `images/` and `labels/`
- **split export**: `train/`, `val|valid/`, `test/`

The `train.py` script handles this automatically:
1. Prepare a normalized local dataset under `data/`
2. Generate `data/dataset.yaml`
3. Start YOLO26 training

## First Test Run (5 epochs)
From this folder run:

```powershell
python .\train.py
```

Or use the shortcut:

```powershell
.\run_train_5epochs.ps1
```

## Defaults
- Model: auto-resolved from dataset task
  - segmentation dataset -> `yolo26n-seg.pt`
  - detection dataset -> `yolo26n.pt`
- Epochs: `5`
- Image size: `640`
- Device: `auto`
- Workers: `0`

## Override Example
```powershell
python .\train.py --epochs 5 --batch 8 --img-size 640 --device 0
```

Prepare a 2-class dataset by remapping source classes during dataset preparation:

```powershell
python .\prepare_dataset.py --class-map "CK=CK,CK-S=NCK,NCK=NCK" --force
```

Or train directly with the same remapping:

```powershell
python .\train.py --epochs 100 --device 0 --class-map "CK=CK,CK-S=NCK,NCK=NCK" --force-prepare
```

Use the same remapping with a split dataset export:

```powershell
python .\train.py --source "Chicken Segmentation.v3i.yolo26" --epochs 100 --device 0 --class-map "CK=CK,CK-S=NCK,NCK=NCK" --force-prepare
```

Prepare a 3-class dataset while oversampling a rare class in the train split:

```powershell
python .\prepare_dataset.py --src "Chicken Segmentation.v3i.yolo26" --dest "data_cks_boost" --oversample-class "CK-S" --oversample-factor 3 --force
```

Train with imbalance controls without merging classes:

```powershell
python .\train.py --source "Chicken Segmentation.v3i.yolo26" --epochs 100 --device 0 --force-prepare --cls-pw 0.5 --copy-paste 0.3 --oversample-class "CK-S" --oversample-factor 3
```

Use a local weight file if you do not want Ultralytics to auto-download:

```powershell
python .\train.py --model D:\models\yolo26n-seg.pt
```

## Generated Output
Prepared dataset:

```text
data/
  images/train
  images/val
  images/test
  labels/train
  labels/val
  labels/test
  dataset.yaml
```

Training outputs:

```text
runs/train/YYYYMMDD_HHMMSS/
  weights/best.pt
  weights/last.pt
  results.csv
```

Hybrid pre-label outputs:

```text
runs/prelabel/YYYYMMDD_HHMMSS/
  data.yaml
  images/... or train|valid|test/images/...
  labels/... or train|valid|test/labels/...
  previews/...
  meta/yolo_detections.json
  meta/annotations.jsonl
  summary.json
```

## Hybrid Pre-Label: YOLO + SAM + Roboflow
Use YOLO for `box + class`, then prompt SAM with each YOLO box to generate cleaner masks.

Recommended for an RTX 2050 4GB laptop:

```powershell
python .\hybrid_prelabel.py `
  --source "D:\your-images" `
  --yolo-model ".\runs\train\20260629_130241\weights\best.pt" `
  --sam-model "mobile_sam.pt" `
  --mask-source hybrid `
  --yolo-device 0 `
  --sam-device cpu
```

Notes:
- `--mask-source hybrid` = YOLO class + SAM mask
- `--mask-source yolo` = export YOLO masks directly without SAM
- `mobile_sam.pt` is the lightest starting point. If you want stronger masks and VRAM allows it, try `sam2_t.pt`.
- The script runs YOLO first, releases that model from memory, then runs SAM. This avoids keeping both models in GPU RAM at once.
- If SAM fails on some detections, the script can fall back to the YOLO mask with `--fallback-yolo-mask`.

### Upload predictions back to Roboflow
Set your API key first:

```powershell
$env:ROBOFLOW_API_KEY="your_api_key"
```

Then run:

```powershell
python .\hybrid_prelabel.py `
  --source "D:\your-images" `
  --yolo-model ".\runs\train\20260629_130241\weights\best.pt" `
  --sam-model "mobile_sam.pt" `
  --mask-source hybrid `
  --yolo-device 0 `
  --sam-device cpu `
  --upload-roboflow `
  --roboflow-workspace "betagro-p5trj" `
  --roboflow-project "chicken-segmentation-pirfa" `
  --roboflow-batch-name "hybrid-prelabel-20260701"
```

If you only want a package for manual upload later, add:

```powershell
--zip-output
```

## Notes
- This dataset is detected as **segmentation** from the label format.
- YOLO26 pretrained weights require `ultralytics>=8.4.0`.
- If `yolo26n-seg.pt` cannot be downloaded automatically, pass a local model path with `--model`.
- `workers=0` is used by default for Windows stability.
- `cls_pw` is Ultralytics inverse-frequency class weighting power: `0.0` disables it, `1.0` applies full inverse-frequency weighting.
- `oversample-factor 3` means each train image containing the target class is written once normally plus 2 extra copies.
