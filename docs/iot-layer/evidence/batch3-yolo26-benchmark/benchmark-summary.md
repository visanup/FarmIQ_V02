# YOLO12 vs YOLO26 Benchmark Summary

Historical context:

- this benchmark was executed before `camera-config/model/best.pt` was overwritten by the promoted YOLO26 candidate
- therefore the baseline path below reflects the historical deployed YOLO12-era artifact at benchmark time
- current runtime no longer uses that historical baseline file path as the active model

- Frozen split: `test`
- Frozen images: `16`
- Baseline model: `D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\iot-layer\camera-config\model\best.pt`
- Candidate model: `D:\FarmIQ_RawData_to_TrainModel\Code-Edge-PRD\FarmIQ_V02\iot-layer\weight-vision-train-model-yolo26\runs\train\20260707_083300\weights\best.pt`

## Segmentation Quality

- Baseline avg best IoU per GT: `0.007437730635317855`
- Candidate avg best IoU per GT: `0.7906766023762447`
- Baseline avg precision@0.5: `0.42857142857142855`
- Candidate avg precision@0.5: `0.7853134613289076`
- Baseline avg recall@0.5: `0.009983766233766234`
- Candidate avg recall@0.5: `0.8993823361030842`

## Runtime Smoke

- Baseline avg latency ms: `1565.52`
- Candidate avg latency ms: `391.40`
