from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
import yaml
from ultralytics import SAM, YOLO


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".avif", ".heic"}
SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class SourceImage:
    source_path: Path
    split: str
    output_image_relative: Path
    output_label_relative: Path


@dataclass(frozen=True)
class DetectionPrompt:
    class_id: int
    class_name: str
    confidence: float
    box_xyxy: list[float]
    yolo_polygon_xyn: list[list[float]] | None


@dataclass(frozen=True)
class ImagePrediction:
    source_path: str
    split: str
    output_image_relative: str
    output_label_relative: str
    image_width: int
    image_height: int
    detections: list[DetectionPrompt]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate hybrid pre-labels using YOLO for box/class and SAM for mask, then optionally upload to Roboflow."
    )
    parser.add_argument("--source", required=True, help="Image folder, flat YOLO export root, or split YOLO export root")
    parser.add_argument(
        "--split",
        choices=["all", "train", "valid", "test"],
        default="all",
        help="When source is a split dataset root, choose which split(s) to process",
    )
    parser.add_argument(
        "--yolo-model",
        default="auto",
        help="YOLO weight path. 'auto' resolves the latest runs/train/*/weights/best.pt",
    )
    parser.add_argument(
        "--sam-model",
        default="mobile_sam.pt",
        help="SAM checkpoint or model name supported by Ultralytics, e.g. mobile_sam.pt or sam2_t.pt",
    )
    parser.add_argument(
        "--mask-source",
        choices=["hybrid", "yolo"],
        default="hybrid",
        help="'hybrid' = YOLO box/class + SAM mask, 'yolo' = export YOLO masks directly",
    )
    parser.add_argument("--img-size", type=int, default=640, help="YOLO inference image size")
    parser.add_argument("--yolo-conf", type=float, default=0.25, help="YOLO confidence threshold")
    parser.add_argument("--yolo-iou", type=float, default=0.7, help="YOLO NMS IoU threshold")
    parser.add_argument("--sam-conf", type=float, default=0.0, help="SAM score threshold")
    parser.add_argument("--max-det", type=int, default=300, help="Maximum detections per image from YOLO")
    parser.add_argument("--max-images", type=int, default=None, help="Optional cap for quick tests")
    parser.add_argument("--yolo-device", default="auto", help="YOLO device: auto, cpu, 0, 0,1")
    parser.add_argument(
        "--sam-device",
        default="cpu",
        help="SAM device. Default cpu is safer on 4GB GPUs. Set 0 to try NVIDIA GPU.",
    )
    parser.add_argument("--output", default="runs/prelabel", help="Base output directory")
    parser.add_argument("--name", default=None, help="Run name under output base. Default YYYYMMDD_HHMMSS")
    parser.add_argument("--force", action="store_true", help="Replace output run directory if it exists")
    parser.add_argument(
        "--save-previews",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Save preview images with polygon overlays",
    )
    parser.add_argument(
        "--fallback-yolo-mask",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When SAM fails for a detection, fall back to the YOLO mask if available",
    )
    parser.add_argument(
        "--simplify-epsilon",
        type=float,
        default=2.0,
        help="Polygon simplification in pixels. Use 0 to disable.",
    )
    parser.add_argument(
        "--min-mask-area",
        type=float,
        default=32.0,
        help="Minimum polygon area in pixels after simplification",
    )
    parser.add_argument("--zip-output", action="store_true", help="Create a zip next to the output directory")
    parser.add_argument("--upload-roboflow", action="store_true", help="Upload generated predictions to Roboflow")
    parser.add_argument("--roboflow-workspace", default=None, help="Roboflow workspace slug")
    parser.add_argument("--roboflow-project", default=None, help="Roboflow project slug")
    parser.add_argument(
        "--roboflow-api-key-env",
        default="ROBOFLOW_API_KEY",
        help="Environment variable holding the Roboflow API key",
    )
    parser.add_argument("--roboflow-batch-name", default=None, help="Roboflow batch/review job name")
    parser.add_argument(
        "--roboflow-split",
        choices=["train", "valid", "test"],
        default=None,
        help="Optional split override for Roboflow upload",
    )
    parser.add_argument(
        "--roboflow-predictions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Upload annotations as predictions instead of ground truth",
    )
    parser.add_argument("--upload-workers", type=int, default=4, help="Parallel upload workers")
    return parser.parse_args()


def _resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (SCRIPT_DIR / path).resolve()


def _default_run_name() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_run_dir(output_arg: str, name_arg: str | None) -> Path:
    base_dir = _resolve_local_path(output_arg)
    run_name = name_arg or _default_run_name()
    return base_dir / run_name


def _prepare_output_dir(run_dir: Path, force: bool) -> None:
    if run_dir.exists():
        if not force:
            raise FileExistsError(f"Output directory already exists: {run_dir}. Use --force to replace it.")
        _remove_tree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)


def _remove_tree(path: Path) -> None:
    def _on_error(func: Any, target: str, exc_info: Any) -> None:
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except Exception:
            raise exc_info[1]

    last_error: Exception | None = None
    for _ in range(3):
        try:
            shutil.rmtree(path, onexc=_on_error)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    if last_error is not None:
        raise last_error


def _iter_image_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _resolve_split_dir(src_dir: Path, split_name: str) -> Path | None:
    candidates = {
        "train": [src_dir / "train" / "images"],
        "valid": [src_dir / "valid" / "images", src_dir / "val" / "images"],
        "test": [src_dir / "test" / "images"],
    }[split_name]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _looks_like_split_dataset(src_dir: Path) -> bool:
    return all(_resolve_split_dir(src_dir, split_name) is not None for split_name in ("train", "valid", "test"))


def _resolve_source_images(src_path: Path, split_arg: str) -> list[SourceImage]:
    if src_path.is_file():
        if src_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Source file is not a supported image: {src_path}")
        return [
            SourceImage(
                source_path=src_path,
                split="train",
                output_image_relative=Path("images") / src_path.name,
                output_label_relative=Path("labels") / src_path.with_suffix(".txt").name,
            )
        ]

    if not src_path.exists() or not src_path.is_dir():
        raise FileNotFoundError(f"Source directory not found: {src_path}")

    if _looks_like_split_dataset(src_path):
        selected_splits = ("train", "valid", "test") if split_arg == "all" else (split_arg,)
        items: list[SourceImage] = []
        for split_name in selected_splits:
            split_dir = _resolve_split_dir(src_path, split_name)
            if split_dir is None:
                continue
            for image_path in _iter_image_files(split_dir):
                relative_path = image_path.relative_to(split_dir)
                items.append(
                    SourceImage(
                        source_path=image_path,
                        split=split_name,
                        output_image_relative=Path(split_name) / "images" / relative_path,
                        output_label_relative=Path(split_name) / "labels" / relative_path.with_suffix(".txt"),
                    )
                )
        if not items:
            raise ValueError(f"No images found under split dataset root: {src_path}")
        return items

    flat_images_dir = src_path / "images"
    if flat_images_dir.exists() and flat_images_dir.is_dir():
        image_root = flat_images_dir
    else:
        image_root = src_path

    images = _iter_image_files(image_root)
    if not images:
        raise ValueError(f"No supported images found in: {image_root}")

    return [
        SourceImage(
            source_path=image_path,
            split="train",
            output_image_relative=Path("images") / image_path.relative_to(image_root),
            output_label_relative=Path("labels") / image_path.relative_to(image_root).with_suffix(".txt"),
        )
        for image_path in images
    ]


def _resolve_yolo_model_path(model_arg: str) -> Path | str:
    if model_arg != "auto":
        resolved = _resolve_local_path(model_arg)
        return resolved if resolved.exists() else model_arg

    train_root = SCRIPT_DIR / "runs" / "train"
    candidates = sorted(
        (
            path / "weights" / "best.pt"
            for path in train_root.iterdir()
            if path.is_dir() and (path / "weights" / "best.pt").exists() and path.name[0:8].isdigit()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            "Could not auto-resolve a trained YOLO weight. Pass --yolo-model with a specific best.pt path."
        )
    return candidates[0]


def _resolve_device(device_arg: str | None, label: str) -> str:
    try:
        import torch
    except Exception as exc:
        raise RuntimeError("PyTorch is required for inference.") from exc

    requested = (device_arg or "auto").strip().lower()
    cuda_available = torch.cuda.is_available()
    torch_version = getattr(torch, "__version__", "unknown")

    if requested == "auto":
        resolved = "0" if cuda_available else "cpu"
    else:
        resolved = requested

    wants_gpu = resolved not in {"cpu", "mps"}
    if wants_gpu and not cuda_available:
        raise RuntimeError(
            f"{label} requested GPU device '{resolved}' but CUDA is not available. torch={torch_version}"
        )

    if resolved == "cpu":
        print(f"{label} device: cpu (torch={torch_version})")
    else:
        device_index = int(resolved.split(",")[0])
        device_name = torch.cuda.get_device_name(device_index)
        print(f"{label} device: cuda:{device_index} ({device_name}, torch={torch_version})")
    return resolved


def _normalize_names(names: Any) -> list[str]:
    if isinstance(names, dict):
        ordered_keys = sorted(names.keys(), key=lambda value: int(value))
        return [str(names[key]) for key in ordered_keys]
    if isinstance(names, list):
        return [str(name) for name in names]
    raise ValueError(f"Unsupported model names object: {type(names)!r}")


def _polygon_array_to_list(polygon: np.ndarray | Sequence[Sequence[float]] | None) -> list[list[float]] | None:
    if polygon is None:
        return None
    array = np.asarray(polygon, dtype=np.float32)
    if array.ndim != 2 or array.shape[0] < 3 or array.shape[1] != 2:
        return None
    if np.allclose(array[0], array[-1]):
        array = array[:-1]
    if array.shape[0] < 3:
        return None
    return [[float(point[0]), float(point[1])] for point in array]


def _simplify_polygon_xyn(
    polygon_xyn: list[list[float]] | None,
    image_width: int,
    image_height: int,
    epsilon_pixels: float,
    min_mask_area: float,
) -> list[list[float]] | None:
    if not polygon_xyn or len(polygon_xyn) < 3:
        return None

    width_scale = max(image_width - 1, 1)
    height_scale = max(image_height - 1, 1)
    points = np.asarray(polygon_xyn, dtype=np.float32)
    points[:, 0] = np.clip(points[:, 0], 0.0, 1.0) * width_scale
    points[:, 1] = np.clip(points[:, 1], 0.0, 1.0) * height_scale

    if epsilon_pixels > 0:
        simplified = cv2.approxPolyDP(points.reshape(-1, 1, 2), epsilon_pixels, True).reshape(-1, 2)
        if simplified.shape[0] >= 3:
            points = simplified

    if points.shape[0] < 3:
        return None

    area = float(abs(cv2.contourArea(points.astype(np.float32))))
    if area < min_mask_area:
        return None

    normalized = points.astype(np.float32)
    normalized[:, 0] = np.clip(normalized[:, 0] / width_scale, 0.0, 1.0)
    normalized[:, 1] = np.clip(normalized[:, 1] / height_scale, 0.0, 1.0)
    return [[float(point[0]), float(point[1])] for point in normalized]


def _format_yolo_segmentation_line(class_id: int, polygon_xyn: list[list[float]]) -> str:
    values = [str(class_id)]
    for x_coord, y_coord in polygon_xyn:
        values.append(f"{x_coord:.6f}")
        values.append(f"{y_coord:.6f}")
    return " ".join(values)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        for row in rows:
            file_handle.write(json.dumps(row, ensure_ascii=False))
            file_handle.write("\n")


def _write_data_yaml(path: Path, class_names: Sequence[str], splits_present: set[str]) -> None:
    data: dict[str, Any] = {
        "task": "segment",
        "nc": len(class_names),
        "names": list(class_names),
    }
    if splits_present == {"train"}:
        data["train"] = "images"
    else:
        if "train" in splits_present:
            data["train"] = "train/images"
        if "valid" in splits_present:
            data["val"] = "valid/images"
        if "test" in splits_present:
            data["test"] = "test/images"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _zip_directory(directory: Path) -> Path:
    zip_path = directory.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                zip_file.write(path, arcname=str(path.relative_to(directory)))
    return zip_path


def _cleanup_torch_device(device: str) -> None:
    if device == "cpu":
        return
    try:
        import gc
        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        return


def _load_image_bgr(image_path: Path) -> np.ndarray:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Could not read image: {image_path}")
    return image


def _draw_preview(
    image_path: Path,
    preview_path: Path,
    detections: Sequence[dict[str, Any]],
    class_names: Sequence[str],
) -> None:
    image = _load_image_bgr(image_path)
    class_count = max(len(class_names), 1)
    for detection in detections:
        class_id = int(detection["class_id"])
        color = (
            int((37 * (class_id + 1)) % 255),
            int((97 * (class_id + 3)) % 255),
            int((17 * (class_id + 5)) % 255),
        )
        polygon_xyn = detection.get("polygon_xyn")
        if polygon_xyn:
            points = np.asarray(
                [
                    [x_coord * max(image.shape[1] - 1, 1), y_coord * max(image.shape[0] - 1, 1)]
                    for x_coord, y_coord in polygon_xyn
                ],
                dtype=np.int32,
            ).reshape(-1, 1, 2)
            cv2.polylines(image, [points], isClosed=True, color=color, thickness=2)

        x1, y1, x2, y2 = [int(round(value)) for value in detection["box_xyxy"]]
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 1)
        label = f"{class_names[class_id]} {detection['confidence']:.2f}"
        cv2.putText(
            image,
            label,
            (x1, max(18, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(preview_path), image):
        raise RuntimeError(f"Could not write preview image: {preview_path}")


def _run_yolo_pass(
    items: Sequence[SourceImage],
    model_path: Path | str,
    yolo_device: str,
    img_size: int,
    yolo_conf: float,
    yolo_iou: float,
    max_det: int,
) -> tuple[list[ImagePrediction], list[str], str]:
    print(f"Loading YOLO model: {model_path}")
    model = YOLO(str(model_path))
    class_names = _normalize_names(model.names)

    predictions: list[ImagePrediction] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        results = model.predict(
            source=str(item.source_path),
            imgsz=img_size,
            conf=yolo_conf,
            iou=yolo_iou,
            max_det=max_det,
            device=yolo_device,
            verbose=False,
            save=False,
            retina_masks=True,
        )
        result = results[0]
        boxes = result.boxes
        mask_polygons = result.masks.xyn if result.masks is not None else []
        detections: list[DetectionPrompt] = []

        detection_count = 0 if boxes is None else len(boxes)
        for detection_index in range(detection_count):
            class_id = int(boxes.cls[detection_index].item())
            detections.append(
                DetectionPrompt(
                    class_id=class_id,
                    class_name=class_names[class_id],
                    confidence=float(boxes.conf[detection_index].item()),
                    box_xyxy=[float(value) for value in boxes.xyxy[detection_index].tolist()],
                    yolo_polygon_xyn=_polygon_array_to_list(
                        mask_polygons[detection_index] if detection_index < len(mask_polygons) else None
                    ),
                )
            )

        predictions.append(
            ImagePrediction(
                source_path=str(item.source_path),
                split=item.split,
                output_image_relative=str(item.output_image_relative),
                output_label_relative=str(item.output_label_relative),
                image_width=int(result.orig_shape[1]),
                image_height=int(result.orig_shape[0]),
                detections=detections,
            )
        )
        print(f"[YOLO {index}/{total}] {item.source_path.name}: {len(detections)} detections")

    del model
    _cleanup_torch_device(yolo_device)
    return predictions, class_names, str(model_path)


def _segment_with_sam_batch(
    sam_model: SAM,
    image_path: Path,
    boxes_xyxy: Sequence[Sequence[float]],
    sam_device: str,
    sam_conf: float,
) -> tuple[list[list[list[float]] | None], list[float | None]]:
    if not boxes_xyxy:
        return [], []

    results = sam_model(
        source=str(image_path),
        bboxes=[list(box) for box in boxes_xyxy],
        device=sam_device,
        conf=sam_conf,
        verbose=False,
        save=False,
    )
    result = results[0]
    polygons = result.masks.xyn if result.masks is not None else []
    scores = result.boxes.conf.tolist() if result.boxes is not None else []

    if len(polygons) == len(boxes_xyxy):
        return (
            [_polygon_array_to_list(polygon) for polygon in polygons],
            [float(score) for score in scores[: len(polygons)]],
        )

    segmented_polygons: list[list[list[float]] | None] = []
    segmented_scores: list[float | None] = []
    for box in boxes_xyxy:
        single_results = sam_model(
            source=str(image_path),
            bboxes=[list(box)],
            device=sam_device,
            conf=sam_conf,
            verbose=False,
            save=False,
        )
        single_result = single_results[0]
        single_polygons = single_result.masks.xyn if single_result.masks is not None else []
        single_scores = single_result.boxes.conf.tolist() if single_result.boxes is not None else []
        segmented_polygons.append(_polygon_array_to_list(single_polygons[0] if single_polygons else None))
        segmented_scores.append(float(single_scores[0]) if single_scores else None)
    return segmented_polygons, segmented_scores


def _build_output_rows(
    prediction: ImagePrediction,
    polygons_by_detection: Sequence[list[list[float]] | None],
    sam_scores: Sequence[float | None],
    class_names: Sequence[str],
    primary_mask_source: str,
    simplify_epsilon: float,
    min_mask_area: float,
    fallback_yolo_mask: bool,
) -> tuple[list[str], list[dict[str, Any]], dict[str, int]]:
    label_lines: list[str] = []
    preview_rows: list[dict[str, Any]] = []
    stats = {"written": 0, "fallback": 0, "skipped": 0, "sam": 0}

    for index, detection in enumerate(prediction.detections):
        polygon_xyn = polygons_by_detection[index] if index < len(polygons_by_detection) else None
        mask_source = primary_mask_source

        if polygon_xyn is None and fallback_yolo_mask:
            polygon_xyn = detection.yolo_polygon_xyn
            mask_source = "yolo-fallback"

        polygon_xyn = _simplify_polygon_xyn(
            polygon_xyn,
            prediction.image_width,
            prediction.image_height,
            epsilon_pixels=simplify_epsilon,
            min_mask_area=min_mask_area,
        )
        if polygon_xyn is None:
            stats["skipped"] += 1
            continue

        if mask_source == "sam":
            stats["sam"] += 1
        elif mask_source == "yolo-fallback":
            stats["fallback"] += 1

        label_lines.append(_format_yolo_segmentation_line(detection.class_id, polygon_xyn))
        preview_rows.append(
            {
                "class_id": detection.class_id,
                "class_name": class_names[detection.class_id],
                "confidence": detection.confidence,
                "sam_score": sam_scores[index] if index < len(sam_scores) else None,
                "box_xyxy": detection.box_xyxy,
                "polygon_xyn": polygon_xyn,
                "mask_source": mask_source,
            }
        )
        stats["written"] += 1

    return label_lines, preview_rows, stats


def _generate_labels(
    predictions: Sequence[ImagePrediction],
    output_dir: Path,
    class_names: Sequence[str],
    mask_source: str,
    sam_model_name: str,
    sam_device: str,
    sam_conf: float,
    simplify_epsilon: float,
    min_mask_area: float,
    fallback_yolo_mask: bool,
    save_previews: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary: dict[str, Any] = {
        "total_images": len(predictions),
        "images_with_detections": 0,
        "detections_total": 0,
        "detections_written": 0,
        "detections_segmented_by_sam": 0,
        "detections_yolo_fallback": 0,
        "detections_skipped": 0,
        "class_counts_written": {class_name: 0 for class_name in class_names},
        "mask_source": mask_source,
        "sam_model": sam_model_name if mask_source == "hybrid" else None,
    }
    upload_rows: list[dict[str, Any]] = []

    sam_model: SAM | None = None
    if mask_source == "hybrid":
        detections_total = sum(len(prediction.detections) for prediction in predictions)
        if detections_total > 0:
            print(f"Loading SAM model: {sam_model_name}")
            sam_model = SAM(sam_model_name)

    total = len(predictions)
    for index, prediction in enumerate(predictions, start=1):
        source_path = Path(prediction.source_path)
        output_image_path = output_dir / prediction.output_image_relative
        output_label_path = output_dir / prediction.output_label_relative
        output_image_path.parent.mkdir(parents=True, exist_ok=True)
        output_label_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, output_image_path)

        summary["detections_total"] += len(prediction.detections)
        if prediction.detections:
            summary["images_with_detections"] += 1

        polygons_by_detection: list[list[list[float]] | None]
        sam_scores: list[float | None]
        if mask_source == "hybrid" and sam_model is not None and prediction.detections:
            polygons_by_detection, sam_scores = _segment_with_sam_batch(
                sam_model=sam_model,
                image_path=source_path,
                boxes_xyxy=[detection.box_xyxy for detection in prediction.detections],
                sam_device=sam_device,
                sam_conf=sam_conf,
            )
        else:
            polygons_by_detection = [detection.yolo_polygon_xyn for detection in prediction.detections]
            sam_scores = [None for _ in prediction.detections]

        label_lines, preview_rows, stats = _build_output_rows(
            prediction=prediction,
            polygons_by_detection=polygons_by_detection,
            sam_scores=sam_scores,
            class_names=class_names,
            primary_mask_source="sam" if mask_source == "hybrid" else "yolo",
            simplify_epsilon=simplify_epsilon,
            min_mask_area=min_mask_area,
            fallback_yolo_mask=fallback_yolo_mask,
        )

        if label_lines:
            _write_text(output_label_path, "\n".join(label_lines) + "\n")
        elif output_label_path.exists():
            output_label_path.unlink()

        if save_previews and preview_rows:
            preview_relative = Path("previews") / Path(prediction.output_image_relative)
            _draw_preview(source_path, output_dir / preview_relative, preview_rows, class_names)

        for row in preview_rows:
            summary["class_counts_written"][row["class_name"]] += 1

        summary["detections_written"] += stats["written"]
        summary["detections_segmented_by_sam"] += stats["sam"]
        summary["detections_yolo_fallback"] += stats["fallback"]
        summary["detections_skipped"] += stats["skipped"]

        upload_rows.append(
            {
                "source_path": str(source_path),
                "output_image_path": str(output_image_path),
                "output_label_path": str(output_label_path) if output_label_path.exists() else None,
                "split": prediction.split,
                "image_width": prediction.image_width,
                "image_height": prediction.image_height,
                "detections_found": len(prediction.detections),
                "detections_written": stats["written"],
                "detections_segmented_by_sam": stats["sam"],
                "detections_yolo_fallback": stats["fallback"],
                "detections_skipped": stats["skipped"],
                "annotations": preview_rows,
            }
        )
        print(
            f"[LABEL {index}/{total}] {source_path.name}: "
            f"found={len(prediction.detections)} written={stats['written']} "
            f"sam={stats['sam']} fallback={stats['fallback']} skipped={stats['skipped']}"
        )

    if sam_model is not None:
        del sam_model
        _cleanup_torch_device(sam_device)

    return upload_rows, summary


def _validate_upload_args(args: argparse.Namespace) -> None:
    if not args.upload_roboflow:
        return
    missing = []
    if not args.roboflow_workspace:
        missing.append("--roboflow-workspace")
    if not args.roboflow_project:
        missing.append("--roboflow-project")
    if missing:
        raise ValueError(f"Roboflow upload requires: {', '.join(missing)}")


def _upload_to_roboflow(output_dir: Path, args: argparse.Namespace) -> dict[str, Any] | None:
    _validate_upload_args(args)
    if not args.upload_roboflow:
        return None

    api_key = os.getenv(args.roboflow_api_key_env)
    if not api_key:
        raise EnvironmentError(
            f"Roboflow upload requested but environment variable {args.roboflow_api_key_env!r} is not set."
        )

    from roboflow import Roboflow

    rf = Roboflow(api_key=api_key)
    workspace = rf.workspace(args.roboflow_workspace)
    workspace.project(args.roboflow_project)
    batch_name = args.roboflow_batch_name or output_dir.name

    print(
        "Uploading predictions to Roboflow: "
        f"workspace={args.roboflow_workspace} project={args.roboflow_project} batch={batch_name}"
    )
    response = workspace.upload_dataset(
        dataset_path=str(output_dir),
        project_name=args.roboflow_project,
        num_workers=args.upload_workers,
        batch_name=batch_name,
        is_prediction=args.roboflow_predictions,
        split=args.roboflow_split,
        use_zip_upload=False,
    )
    return {
        "workspace": args.roboflow_workspace,
        "project": args.roboflow_project,
        "batch_name": batch_name,
        "split": args.roboflow_split,
        "is_prediction": args.roboflow_predictions,
        "response": response,
    }


def _validate_args(args: argparse.Namespace) -> None:
    if args.max_det < 1:
        raise ValueError(f"--max-det must be >= 1, got {args.max_det}")
    if args.max_images is not None and args.max_images < 1:
        raise ValueError(f"--max-images must be >= 1, got {args.max_images}")
    if not 0.0 <= args.yolo_conf <= 1.0:
        raise ValueError(f"--yolo-conf must be between 0.0 and 1.0, got {args.yolo_conf}")
    if not 0.0 <= args.yolo_iou <= 1.0:
        raise ValueError(f"--yolo-iou must be between 0.0 and 1.0, got {args.yolo_iou}")
    if not 0.0 <= args.sam_conf <= 1.0:
        raise ValueError(f"--sam-conf must be between 0.0 and 1.0, got {args.sam_conf}")
    if args.simplify_epsilon < 0:
        raise ValueError(f"--simplify-epsilon must be >= 0, got {args.simplify_epsilon}")
    if args.min_mask_area < 0:
        raise ValueError(f"--min-mask-area must be >= 0, got {args.min_mask_area}")
    _validate_upload_args(args)


def main() -> int:
    args = _parse_args()
    _validate_args(args)

    source_path = _resolve_local_path(args.source)
    run_dir = _resolve_run_dir(args.output, args.name)
    _prepare_output_dir(run_dir, args.force)

    yolo_device = _resolve_device(args.yolo_device, label="YOLO")
    sam_device = _resolve_device(args.sam_device, label="SAM") if args.mask_source == "hybrid" else "cpu"

    items = _resolve_source_images(source_path, args.split)
    if args.max_images is not None:
        items = items[: args.max_images]

    yolo_model_path = _resolve_yolo_model_path(args.yolo_model)
    predictions, class_names, resolved_yolo_model = _run_yolo_pass(
        items=items,
        model_path=yolo_model_path,
        yolo_device=yolo_device,
        img_size=args.img_size,
        yolo_conf=args.yolo_conf,
        yolo_iou=args.yolo_iou,
        max_det=args.max_det,
    )

    _write_json(
        run_dir / "meta" / "yolo_detections.json",
        [
            {
                **asdict(prediction),
                "detections": [asdict(detection) for detection in prediction.detections],
            }
            for prediction in predictions
        ],
    )

    upload_rows, label_summary = _generate_labels(
        predictions=predictions,
        output_dir=run_dir,
        class_names=class_names,
        mask_source=args.mask_source,
        sam_model_name=args.sam_model,
        sam_device=sam_device,
        sam_conf=args.sam_conf,
        simplify_epsilon=args.simplify_epsilon,
        min_mask_area=args.min_mask_area,
        fallback_yolo_mask=args.fallback_yolo_mask,
        save_previews=args.save_previews,
    )

    splits_present = {prediction.split for prediction in predictions}
    _write_data_yaml(run_dir / "data.yaml", class_names, splits_present)
    _write_jsonl(run_dir / "meta" / "annotations.jsonl", upload_rows)

    summary: dict[str, Any] = {
        "source": str(source_path),
        "output_dir": str(run_dir),
        "yolo_model": resolved_yolo_model,
        "sam_model": args.sam_model if args.mask_source == "hybrid" else None,
        "mask_source": args.mask_source,
        "yolo_device": yolo_device,
        "sam_device": sam_device if args.mask_source == "hybrid" else None,
        "class_names": class_names,
        "settings": {
            "img_size": args.img_size,
            "yolo_conf": args.yolo_conf,
            "yolo_iou": args.yolo_iou,
            "sam_conf": args.sam_conf,
            "simplify_epsilon": args.simplify_epsilon,
            "min_mask_area": args.min_mask_area,
            "fallback_yolo_mask": args.fallback_yolo_mask,
        },
        "result": label_summary,
    }

    if args.zip_output:
        zip_path = _zip_directory(run_dir)
        summary["zip_path"] = str(zip_path)

    if args.upload_roboflow:
        upload_result = _upload_to_roboflow(run_dir, args)
        summary["roboflow_upload"] = upload_result
        _write_json(run_dir / "meta" / "roboflow_upload.json", upload_result)

    _write_json(run_dir / "summary.json", summary)

    print(f"Hybrid pre-label complete. Output: {run_dir}")
    print("Summary:")
    print(f"- images: {label_summary['total_images']}")
    print(f"- detections_found: {label_summary['detections_total']}")
    print(f"- detections_written: {label_summary['detections_written']}")
    print(f"- detections_segmented_by_sam: {label_summary['detections_segmented_by_sam']}")
    print(f"- detections_yolo_fallback: {label_summary['detections_yolo_fallback']}")
    print(f"- detections_skipped: {label_summary['detections_skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
