from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from prepare_dataset import prepare_dataset


SCRIPT_DIR = Path(__file__).resolve().parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLO26 from the local FarmIQ dataset.")
    parser.add_argument("--source", default="Chicken Segmentation.yolo26", help="Source dataset directory")
    parser.add_argument("--data", default="data/dataset.yaml", help="Prepared dataset.yaml path")
    parser.add_argument("--model", default="auto", help="YOLO26 base model name or local path")
    parser.add_argument("--task", choices=["auto", "detect", "segment"], default="auto")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--img-size", type=int, default=640)
    parser.add_argument("--device", default="auto", help="Device id (e.g. 0), 'cpu', or 'auto'")
    parser.add_argument("--project", default="runs/train", help="Base output directory")
    parser.add_argument("--name", default=None, help="Run name (default: YYYYMMDD_HHMMSS)")
    parser.add_argument("--workers", type=int, default=0, help="Dataloader workers; use 0 on Windows")
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True, help="Enable AMP mixed precision")
    parser.add_argument(
        "--cls-pw",
        type=float,
        default=0.0,
        help="Class-weight power for imbalance handling. 0.0 disables, 1.0 = full inverse-frequency weighting.",
    )
    parser.add_argument(
        "--copy-paste",
        type=float,
        default=0.0,
        help="Segmentation copy-paste augmentation probability. Use 0.0 to disable.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--class-map",
        default=None,
        help='Optional class remapping passed to prepare_dataset, e.g. "CK=CK,CK-S=NCK,NCK=NCK"',
    )
    parser.add_argument(
        "--oversample-class",
        default=None,
        help='Optional class name(s) to oversample in the prepared train split, e.g. "CK-S"',
    )
    parser.add_argument(
        "--oversample-factor",
        type=int,
        default=1,
        help="Total train copies for matching images. Example: 3 = original + 2 extra copies.",
    )
    parser.add_argument("--force-prepare", action="store_true", help="Recreate prepared dataset split")
    parser.add_argument("--skip-prepare", action="store_true", help="Skip dataset preparation step")
    return parser.parse_args()


def _resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (SCRIPT_DIR / path).resolve()


def _default_run_name() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_run_dir(train_results: Any, project: str, name: str) -> Path:
    if hasattr(train_results, "save_dir") and train_results.save_dir:
        return Path(train_results.save_dir)
    return Path(project) / name


def _resolve_device(device_arg: str | None) -> str:
    try:
        import torch
    except Exception as exc:
        raise RuntimeError("PyTorch is required before training.") from exc

    requested = (device_arg or "auto").strip().lower()
    cuda_available = torch.cuda.is_available()
    torch_version = getattr(torch, "__version__", "unknown")

    if requested == "auto":
        resolved = "0" if cuda_available else "cpu"
    else:
        resolved = requested

    wants_gpu = resolved not in ("cpu", "mps")
    if wants_gpu and not cuda_available:
        raise RuntimeError(
            "GPU training was requested but CUDA is not available in this Python environment. "
            f"Current torch build: {torch_version}. Install a CUDA-enabled PyTorch build, then rerun with --device 0."
        )

    if resolved == "cpu":
        print(f"Training device: cpu (torch={torch_version})")
    else:
        device_index = int(resolved.split(",")[0])
        device_name = torch.cuda.get_device_name(device_index)
        print(f"Training device: cuda:{device_index} ({device_name}, torch={torch_version})")

    return resolved


def _read_dataset_task(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("task:"):
            value = stripped.split(":", 1)[1].strip()
            if value in ("segment", "seg"):
                return "segment"
            if value in ("detect", "detection"):
                return "detect"
    return None


def _resolve_task(task_arg: str, data_path: Path) -> str:
    if task_arg != "auto":
        return task_arg
    detected = _read_dataset_task(data_path)
    return detected or "detect"


def _resolve_model(model_arg: str, task: str) -> str:
    if model_arg != "auto":
        return model_arg
    return "yolo26n-seg.pt" if task == "segment" else "yolo26n.pt"


def _validate_training_args(args: argparse.Namespace) -> None:
    if not 0.0 <= args.cls_pw <= 1.0:
        raise ValueError(f"--cls-pw must be between 0.0 and 1.0, got {args.cls_pw}")
    if not 0.0 <= args.copy_paste <= 1.0:
        raise ValueError(f"--copy-paste must be between 0.0 and 1.0, got {args.copy_paste}")
    if args.oversample_factor < 1:
        raise ValueError(f"--oversample-factor must be >= 1, got {args.oversample_factor}")


def _read_results_csv(run_dir: Path) -> dict[str, float] | None:
    results_csv = run_dir / "results.csv"
    if not results_csv.exists():
        return None

    with results_csv.open("r", newline="", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle)
        rows = list(reader)
    if not rows:
        return None

    last = rows[-1]
    metrics_map = {
        "precision_box": ["metrics/precision(B)", "metrics/precision"],
        "recall_box": ["metrics/recall(B)", "metrics/recall"],
        "mAP50_box": ["metrics/mAP50(B)", "metrics/mAP50"],
        "mAP50-95_box": ["metrics/mAP50-95(B)", "metrics/mAP50-95"],
        "precision_mask": ["metrics/precision(M)", "metrics/precision(mask)"],
        "recall_mask": ["metrics/recall(M)", "metrics/recall(mask)"],
        "mAP50_mask": ["metrics/mAP50(M)", "metrics/mAP50(mask)"],
        "mAP50-95_mask": ["metrics/mAP50-95(M)", "metrics/mAP50-95(mask)"],
    }

    output: dict[str, float] = {}
    for label, keys in metrics_map.items():
        for key in keys:
            if key in last and last[key] != "":
                try:
                    output[label] = float(last[key])
                except ValueError:
                    pass
                break
    return output or None


def _print_metrics(run_dir: Path) -> None:
    metrics = _read_results_csv(run_dir)
    if not metrics:
        print("Final metrics not found in results.csv. Check training logs.")
        return

    print("Final metrics:")
    for key, value in metrics.items():
        print(f"- {key}: {value:.4f}")


def _patch_ultralytics_cache_labels() -> None:
    from ultralytics.data import dataset as dataset_module
    from ultralytics.data.utils import get_hash, verify_image_label

    if getattr(dataset_module.YOLODataset.cache_labels, "__name__", "") == "_cache_labels_sequential":
        return

    def _cache_labels_sequential(self: Any, path: Path = Path("./labels.cache")) -> dict:
        cache = {"labels": []}
        missing, found, empty, corrupt, messages = 0, 0, 0, 0, []
        keypoint_count, keypoint_dims = self.data.get("kpt_shape", (0, 0))
        if self.use_keypoints and (keypoint_count <= 0 or keypoint_dims not in {2, 3}):
            raise ValueError("'kpt_shape' in data.yaml missing or incorrect. Should be [number of keypoints, dims].")

        for args in zip(
            self.im_files,
            self.label_files,
            [self.prefix] * len(self.im_files),
            [self.use_keypoints] * len(self.im_files),
            [len(self.data["names"])] * len(self.im_files),
            [keypoint_count] * len(self.im_files),
            [keypoint_dims] * len(self.im_files),
            [self.single_cls] * len(self.im_files),
        ):
            im_file, label_data, shape, segments, keypoints, miss_i, found_i, empty_i, corrupt_i, message = verify_image_label(args)
            missing += miss_i
            found += found_i
            empty += empty_i
            corrupt += corrupt_i
            if im_file:
                cache["labels"].append(
                    {
                        "im_file": im_file,
                        "shape": shape,
                        "cls": label_data[:, 0:1],
                        "bboxes": label_data[:, 1:],
                        "segments": segments,
                        "keypoints": keypoints,
                        "normalized": True,
                        "bbox_format": "xywh",
                    }
                )
            if message:
                messages.append(message)

        cache["hash"] = get_hash(self.label_files + self.im_files)
        cache["results"] = found, missing, empty, corrupt, len(self.im_files)
        cache["msgs"] = messages
        cache["version"] = dataset_module.DATASET_CACHE_VERSION
        return cache

    dataset_module.YOLODataset.cache_labels = _cache_labels_sequential


def _prepare_dataset_if_needed(args: argparse.Namespace) -> Path:
    data_path = _resolve_local_path(args.data)
    if args.skip_prepare and data_path.exists():
        return data_path

    prepared = prepare_dataset(
        src_dir=_resolve_local_path(args.source),
        dest_dir=data_path.parent,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
        task_arg=args.task,
        class_map=args.class_map,
        oversample_class=args.oversample_class,
        oversample_factor=args.oversample_factor,
        force=args.force_prepare,
    )
    print(
        "Prepared dataset "
        f"(task={prepared.task}, total={prepared.total_images}, "
        f"train={prepared.train_count}, val={prepared.val_count}, test={prepared.test_count})"
    )
    if prepared.extra_train_copies:
        print(
            f"Oversampling applied: source_total={prepared.source_total_images}, "
            f"extra_train_copies={prepared.extra_train_copies}"
        )
    return prepared.dataset_yaml


def train_yolo(args: argparse.Namespace) -> Path:
    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError("Ultralytics is required. Install or update `ultralytics`.") from exc

    _validate_training_args(args)
    data_path = _prepare_dataset_if_needed(args)
    task = _resolve_task(args.task, data_path)
    model_name = _resolve_model(args.model, task)
    device = _resolve_device(args.device)
    _patch_ultralytics_cache_labels()

    print(f"Dataset task: {task}")
    print(f"Base model: {model_name}")
    print(f"Imbalance controls: cls_pw={args.cls_pw}, copy_paste={args.copy_paste}")

    run_name = args.name or _default_run_name()
    project_dir = _resolve_local_path(args.project)

    try:
        model = YOLO(model_name)
    except Exception as exc:
        raise RuntimeError(
            f"Could not load model '{model_name}'. "
            "If automatic download is blocked, pass a local .pt path via --model."
        ) from exc

    model_task = getattr(model, "task", None)
    if task == "segment" and model_task not in (None, "segment", "seg"):
        print("[WARN] Dataset is segmentation, but the selected model does not look like a segmentation model.")
    if task == "detect" and model_task in ("segment", "seg"):
        print("[WARN] Dataset is detection, but the selected model looks like a segmentation model.")

    train_results = model.train(
        data=str(data_path.resolve()),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.img_size,
        device=device,
        project=str(project_dir),
        name=run_name,
        exist_ok=False,
        workers=args.workers,
        amp=args.amp,
        cls_pw=args.cls_pw,
        copy_paste=args.copy_paste,
    )

    return _resolve_run_dir(train_results, str(project_dir), run_name)


def main() -> int:
    args = _parse_args()
    run_dir = train_yolo(args)
    print(f"Training complete. Output: {run_dir}")
    _print_metrics(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
