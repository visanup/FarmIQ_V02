from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from model_runtime import list_model_profiles, resolve_model_profile
from yolo_infer import UltralyticsSegDetector


def _candidate_paths() -> list[Path]:
    return [
        Path(__file__).resolve().parents[1] / "weight-vision-train-model-yolo26" / "yolo26n-seg.pt",
        Path(__file__).resolve().parents[1]
        / "weight-vision-train-model-yolo26"
        / "runs"
        / "train"
        / "20260707_083300"
        / "weights"
        / "best.pt",
    ]


def _default_image() -> Path:
    test_dir = (
        Path(__file__).resolve().parents[1]
        / "weight-vision-train-model-yolo26"
        / "Chicken Segmentation.v4i.yolo26"
        / "test"
        / "images"
    )
    candidates = sorted(test_dir.glob("*.jpg"))
    if not candidates:
        raise FileNotFoundError(f"No sample images found in {test_dir}")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a lightweight runtime compatibility check for Ultralytics segmentation models."
    )
    parser.add_argument("--model-config", default=None, help="Optional runtime-config.yaml path")
    parser.add_argument(
        "--model-id",
        action="append",
        default=[],
        help="Configured model profile ID to verify. Can be provided multiple times.",
    )
    parser.add_argument(
        "--model-path",
        action="append",
        default=[],
        help="Explicit model path to verify. Can be provided multiple times.",
    )
    parser.add_argument("--image", default=None, help="Sample image path for smoke inference")
    parser.add_argument("--output", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    image_path = Path(args.image).resolve() if args.image else _default_image()
    if not image_path.exists():
        raise FileNotFoundError(f"Sample image not found: {image_path}")

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None or image_bgr.size == 0:
        raise RuntimeError(f"Failed to load sample image: {image_path}")

    requested: list[tuple[str | None, str | None]] = []
    for configured_id in args.model_id:
        requested.append((configured_id, None))
    for explicit_path in args.model_path:
        requested.append((None, explicit_path))

    if not requested:
        configured = list_model_profiles(
            Path(args.model_config).resolve() if args.model_config else None
        )
        if configured:
            requested.extend((profile.model_id, None) for profile in configured)
        for candidate_path in _candidate_paths():
            if candidate_path.exists():
                requested.append((None, str(candidate_path)))

    seen_paths: set[str] = set()
    rows = []
    for configured_id, explicit_path in requested:
        profile = resolve_model_profile(
            model=explicit_path,
            model_id=configured_id,
            model_config=args.model_config,
        )
        resolved_path = str(profile.path.resolve())
        if resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)

        detector = UltralyticsSegDetector(
            model_path=str(profile.path),
            conf=profile.conf if profile.conf is not None else 0.25,
            iou=profile.iou if profile.iou is not None else 0.45,
            imgsz=profile.imgsz,
            device=profile.device,
        )
        detections = detector.predict(image_bgr)
        rows.append(
            {
                "model_id": profile.model_id,
                "path": str(profile.path),
                "source": profile.source,
                "family": profile.family,
                "task": detector.model.task,
                "image": str(image_path),
                "detections": len(detections),
                "has_mask_xy": any(det.mask_xy for det in detections),
                "sample_detection": (
                    {
                        "xyxy": list(detections[0].xyxy),
                        "conf": detections[0].conf,
                        "cls": detections[0].cls,
                        "mask_points": len(detections[0].mask_xy or []),
                    }
                    if detections
                    else None
                ),
            }
        )

    payload = {"image": str(image_path), "results": rows}
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
