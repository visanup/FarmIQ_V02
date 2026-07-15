from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from ultralytics import YOLO

from model_runtime import resolve_model_profile


def _load_dataset_config(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise RuntimeError(f"Invalid dataset yaml: {path}")
    return raw


def _resolve_split_images(dataset_yaml: Path, split: str) -> list[Path]:
    data = _load_dataset_config(dataset_yaml)
    dataset_root = dataset_yaml.parent
    split_value = data.get(split)
    if not isinstance(split_value, str):
        raise KeyError(f"Dataset yaml {dataset_yaml} has no split '{split}'")

    images_dir = _resolve_images_dir(dataset_root, split, split_value)
    return sorted(
        [
            path
            for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ]
    )


def _resolve_images_dir(dataset_root: Path, split: str, split_value: str) -> Path:
    candidates = [
        (dataset_root / split_value).resolve(),
        (dataset_root / split_value.lstrip("./")).resolve(),
    ]

    split_dir_alias = {"train": "train", "val": "valid", "test": "test"}
    split_dir_name = split_dir_alias.get(split, split)
    candidates.extend(
        [
            (dataset_root / split_dir_name / "images").resolve(),
            (dataset_root / split_dir_name).resolve(),
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists() and candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        f"Split path not found for split '{split}'. Checked: {', '.join(str(path) for path in seen)}"
    )


def _label_path_for_image(image_path: Path) -> Path:
    split_dir = image_path.parent.parent
    labels_dir = split_dir / "labels"
    return labels_dir / f"{image_path.stem}.txt"


def _freeze_subset(dataset_yaml: Path, split: str, max_images: int, output_dir: Path) -> tuple[Path, list[Path]]:
    source_images = _resolve_split_images(dataset_yaml, split)
    selected = source_images[:max_images]
    if not selected:
        raise RuntimeError(f"No images available for split '{split}' in {dataset_yaml}")

    frozen_root = output_dir / "frozen_dataset"
    images_dir = frozen_root / split / "images"
    labels_dir = frozen_root / split / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    for image_path in selected:
        shutil.copy2(image_path, images_dir / image_path.name)
        label_path = _label_path_for_image(image_path)
        if label_path.exists():
            shutil.copy2(label_path, labels_dir / label_path.name)

    dataset_payload = {
        "path": str(frozen_root),
        "train": f"{split}/images",
        "val": f"{split}/images",
        "test": f"{split}/images",
        "task": "segment",
        "nc": _load_dataset_config(dataset_yaml).get("nc"),
        "names": _load_dataset_config(dataset_yaml).get("names"),
    }
    frozen_yaml = frozen_root / "dataset.yaml"
    frozen_yaml.write_text(yaml.safe_dump(dataset_payload, sort_keys=False), encoding="utf-8")
    return frozen_yaml, selected


@dataclass
class MaskObject:
    cls: int
    polygon_xy: list[list[float]]
    conf: float | None = None


def _parse_ground_truth_objects(label_path: Path, image_shape: tuple[int, int]) -> list[MaskObject]:
    height, width = image_shape
    if not label_path.exists():
        return []

    objects: list[MaskObject] = []
    for raw_line in label_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 7 or (len(parts) - 1) % 2 != 0:
            continue
        try:
            class_id = int(float(parts[0]))
            coords = [float(value) for value in parts[1:]]
        except ValueError:
            continue
        polygon_xy = [
            [coords[index] * width, coords[index + 1] * height]
            for index in range(0, len(coords), 2)
        ]
        if len(polygon_xy) >= 3:
            objects.append(MaskObject(cls=class_id, polygon_xy=polygon_xy))
    return objects


def _prediction_objects(result: Any) -> list[MaskObject]:
    boxes = getattr(result, "boxes", None)
    masks = getattr(result, "masks", None)
    if boxes is None or masks is None or getattr(masks, "xy", None) is None:
        return []

    confs = boxes.conf.cpu().numpy() if getattr(boxes, "conf", None) is not None else None
    classes = boxes.cls.cpu().numpy() if getattr(boxes, "cls", None) is not None else None
    polygons = masks.xy
    objects: list[MaskObject] = []
    for index, polygon in enumerate(polygons):
        if polygon is None or len(polygon) < 3:
            continue
        class_id = int(classes[index]) if classes is not None and index < len(classes) else -1
        conf = float(confs[index]) if confs is not None and index < len(confs) else None
        points = [[float(x), float(y)] for x, y in polygon]
        objects.append(MaskObject(cls=class_id, polygon_xy=points, conf=conf))
    return objects


def _polygon_to_mask(polygon_xy: list[list[float]], image_shape: tuple[int, int]) -> np.ndarray:
    height, width = image_shape
    mask = np.zeros((height, width), dtype=np.uint8)
    pts = np.array(polygon_xy, dtype=np.float32).round().astype(np.int32).reshape((-1, 1, 2))
    pts[:, 0, 0] = np.clip(pts[:, 0, 0], 0, max(0, width - 1))
    pts[:, 0, 1] = np.clip(pts[:, 0, 1], 0, max(0, height - 1))
    cv2.fillPoly(mask, [pts], 1)
    return mask


def _mask_iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    intersection = int(np.logical_and(mask_a, mask_b).sum())
    union = int(np.logical_or(mask_a, mask_b).sum())
    if union == 0:
        return 0.0
    return float(intersection / union)


def _evaluate_predictions(
    ground_truth: list[MaskObject],
    predicted: list[MaskObject],
    image_shape: tuple[int, int],
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    gt_masks = [_polygon_to_mask(obj.polygon_xy, image_shape) for obj in ground_truth]
    pred_masks = [_polygon_to_mask(obj.polygon_xy, image_shape) for obj in predicted]

    candidate_pairs: list[tuple[float, int, int]] = []
    best_iou_per_gt = [0.0 for _ in ground_truth]
    for gt_index, gt_obj in enumerate(ground_truth):
        for pred_index, pred_obj in enumerate(predicted):
            if gt_obj.cls != pred_obj.cls:
                continue
            iou = _mask_iou(gt_masks[gt_index], pred_masks[pred_index])
            if iou > best_iou_per_gt[gt_index]:
                best_iou_per_gt[gt_index] = iou
            candidate_pairs.append((iou, gt_index, pred_index))

    candidate_pairs.sort(key=lambda row: row[0], reverse=True)
    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    matched_ious: list[float] = []
    for iou, gt_index, pred_index in candidate_pairs:
        if iou < iou_threshold:
            break
        if gt_index in matched_gt or pred_index in matched_pred:
            continue
        matched_gt.add(gt_index)
        matched_pred.add(pred_index)
        matched_ious.append(iou)

    tp = len(matched_ious)
    fp = max(0, len(predicted) - tp)
    fn = max(0, len(ground_truth) - tp)
    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else None
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else None

    return {
        "ground_truth_objects": len(ground_truth),
        "predicted_objects": len(predicted),
        "true_positive_at_iou_0_5": tp,
        "false_positive_at_iou_0_5": fp,
        "false_negative_at_iou_0_5": fn,
        "precision_at_iou_0_5": precision,
        "recall_at_iou_0_5": recall,
        "mean_best_iou_per_gt": (
            float(sum(best_iou_per_gt) / len(best_iou_per_gt)) if best_iou_per_gt else None
        ),
        "mean_matched_iou_at_0_5": (
            float(sum(matched_ious) / len(matched_ious)) if matched_ious else None
        ),
    }


def _run_prediction_smoke(
    model: YOLO,
    image_paths: list[Path],
    conf: float,
    iou: float,
    imgsz: int,
    device: str | None,
) -> dict[str, Any]:
    timings_ms: list[float] = []
    total_detections = 0
    mean_conf_samples: list[float] = []
    mask_detection_count = 0
    per_image_quality: list[dict[str, Any]] = []

    for image_path in image_paths:
        image_bgr = cv2.imread(str(image_path))
        if image_bgr is None or image_bgr.size == 0:
            raise RuntimeError(f"Failed to load image for benchmark: {image_path}")
        image_shape = image_bgr.shape[:2]
        start = time.perf_counter()
        results = model.predict(
            source=image_bgr,
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            device=device,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        timings_ms.append(elapsed_ms)

        result = results[0]
        boxes = getattr(result, "boxes", None)
        box_count = len(boxes) if boxes is not None else 0
        total_detections += box_count
        if boxes is not None and getattr(boxes, "conf", None) is not None and box_count > 0:
            conf_tensor = boxes.conf
            try:
                mean_conf_samples.append(float(conf_tensor.mean().item()))
            except Exception:
                pass
        masks = getattr(result, "masks", None)
        if masks is not None and getattr(masks, "xy", None) is not None:
            mask_detection_count += len(masks.xy)

        ground_truth_objects = _parse_ground_truth_objects(_label_path_for_image(image_path), image_shape)
        predicted_objects = _prediction_objects(result)
        quality = _evaluate_predictions(ground_truth_objects, predicted_objects, image_shape)
        quality["image"] = str(image_path)
        per_image_quality.append(quality)

    precision_values = [
        row["precision_at_iou_0_5"]
        for row in per_image_quality
        if row["precision_at_iou_0_5"] is not None
    ]
    recall_values = [
        row["recall_at_iou_0_5"]
        for row in per_image_quality
        if row["recall_at_iou_0_5"] is not None
    ]
    best_iou_values = [
        row["mean_best_iou_per_gt"]
        for row in per_image_quality
        if row["mean_best_iou_per_gt"] is not None
    ]
    matched_iou_values = [
        row["mean_matched_iou_at_0_5"]
        for row in per_image_quality
        if row["mean_matched_iou_at_0_5"] is not None
    ]

    return {
        "images": len(image_paths),
        "avg_latency_ms": sum(timings_ms) / len(timings_ms),
        "max_latency_ms": max(timings_ms),
        "min_latency_ms": min(timings_ms),
        "total_detections": total_detections,
        "avg_detections_per_image": total_detections / len(image_paths),
        "avg_confidence": (
            sum(mean_conf_samples) / len(mean_conf_samples) if mean_conf_samples else None
        ),
        "mask_detection_count": mask_detection_count,
        "quality": {
            "avg_precision_at_iou_0_5": (
                float(sum(precision_values) / len(precision_values)) if precision_values else None
            ),
            "avg_recall_at_iou_0_5": (
                float(sum(recall_values) / len(recall_values)) if recall_values else None
            ),
            "avg_mean_best_iou_per_gt": (
                float(sum(best_iou_values) / len(best_iou_values)) if best_iou_values else None
            ),
            "avg_mean_matched_iou_at_0_5": (
                float(sum(matched_iou_values) / len(matched_iou_values)) if matched_iou_values else None
            ),
            "per_image": per_image_quality,
        },
    }


def _evaluate_model(
    model_id: str,
    model_path: Path,
    data_yaml: Path,
    split: str,
    conf: float,
    iou: float,
    imgsz: int,
    device: str | None,
    sample_images: list[Path],
    output_dir: Path,
) -> dict[str, Any]:
    model = YOLO(str(model_path))
    del data_yaml
    del split
    del output_dir
    return {
        "model_id": model_id,
        "model_path": str(model_path),
        "task": getattr(model, "task", None),
        "prediction_smoke": _run_prediction_smoke(model, sample_images, conf, iou, imgsz, device),
    }


def _build_summary(report: dict[str, Any]) -> str:
    baseline = report["baseline"]
    candidate = report["candidate"]
    baseline_latency = baseline["prediction_smoke"]["avg_latency_ms"]
    candidate_latency = candidate["prediction_smoke"]["avg_latency_ms"]
    baseline_best_iou = baseline["prediction_smoke"]["quality"].get("avg_mean_best_iou_per_gt")
    candidate_best_iou = candidate["prediction_smoke"]["quality"].get("avg_mean_best_iou_per_gt")
    baseline_precision = baseline["prediction_smoke"]["quality"].get("avg_precision_at_iou_0_5")
    candidate_precision = candidate["prediction_smoke"]["quality"].get("avg_precision_at_iou_0_5")
    baseline_recall = baseline["prediction_smoke"]["quality"].get("avg_recall_at_iou_0_5")
    candidate_recall = candidate["prediction_smoke"]["quality"].get("avg_recall_at_iou_0_5")

    lines = [
        "# YOLO12 vs YOLO26 Benchmark Summary",
        "",
        f"- Frozen split: `{report['frozen_split']}`",
        f"- Frozen images: `{report['frozen_image_count']}`",
        f"- Baseline model: `{baseline['model_path']}`",
        f"- Candidate model: `{candidate['model_path']}`",
        "",
        "## Segmentation Quality",
        "",
        f"- Baseline avg best IoU per GT: `{baseline_best_iou}`",
        f"- Candidate avg best IoU per GT: `{candidate_best_iou}`",
        f"- Baseline avg precision@0.5: `{baseline_precision}`",
        f"- Candidate avg precision@0.5: `{candidate_precision}`",
        f"- Baseline avg recall@0.5: `{baseline_recall}`",
        f"- Candidate avg recall@0.5: `{candidate_recall}`",
        "",
        "## Runtime Smoke",
        "",
        f"- Baseline avg latency ms: `{baseline_latency:.2f}`",
        f"- Candidate avg latency ms: `{candidate_latency:.2f}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze a small evaluation subset and compare two segmentation models on the same dataset."
    )
    parser.add_argument("--model-config", default=None, help="Optional runtime-config.yaml path")
    parser.add_argument("--baseline-model", default=None, help="Explicit baseline model path")
    parser.add_argument("--baseline-model-id", default=None, help="Configured baseline model profile ID")
    parser.add_argument("--candidate-model", default=None, help="Explicit candidate model path")
    parser.add_argument("--candidate-model-id", default=None, help="Configured candidate model profile ID")
    parser.add_argument(
        "--data-yaml",
        default="D:/FarmIQ_RawData_to_TrainModel/Code-Edge-PRD/FarmIQ_V02/iot-layer/weight-vision-train-model-yolo26/Chicken Segmentation.v4i.yolo26/data.yaml",
        help="Dataset yaml path",
    )
    parser.add_argument("--split", default="test", help="Dataset split to freeze")
    parser.add_argument("--max-images", type=int, default=16, help="Number of images to freeze for comparison")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--device", default=None)
    parser.add_argument(
        "--output-dir",
        default="D:/FarmIQ_RawData_to_TrainModel/Code-Edge-PRD/FarmIQ_V02/docs/iot-layer/evidence/batch3-yolo26-benchmark",
        help="Output directory for frozen dataset and reports",
    )
    args = parser.parse_args()

    baseline_profile = resolve_model_profile(
        model=args.baseline_model,
        model_id=args.baseline_model_id,
        model_config=args.model_config,
    )
    candidate_profile = resolve_model_profile(
        model=args.candidate_model,
        model_id=args.candidate_model_id,
        model_config=args.model_config,
    )

    dataset_yaml = Path(args.data_yaml).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    frozen_yaml, selected_images = _freeze_subset(dataset_yaml, args.split, args.max_images, output_dir)
    frozen_images = sorted((frozen_yaml.parent / args.split / "images").glob("*"))

    report = {
        "frozen_dataset_yaml": str(frozen_yaml),
        "frozen_split": args.split,
        "frozen_image_count": len(frozen_images),
        "baseline": _evaluate_model(
            baseline_profile.model_id,
            baseline_profile.path,
            frozen_yaml,
            "test",
            args.conf,
            args.iou,
            args.imgsz,
            args.device,
            frozen_images,
            output_dir,
        ),
        "candidate": _evaluate_model(
            candidate_profile.model_id,
            candidate_profile.path,
            frozen_yaml,
            "test",
            args.conf,
            args.iou,
            args.imgsz,
            args.device,
            frozen_images,
            output_dir,
        ),
        "source_images": [str(path) for path in selected_images],
    }

    json_path = output_dir / "benchmark-report.json"
    md_path = output_dir / "benchmark-summary.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(_build_summary(report), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
