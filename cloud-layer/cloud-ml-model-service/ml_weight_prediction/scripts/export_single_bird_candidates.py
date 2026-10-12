"""Create an object-storage download manifest for single-bird label candidates.

Candidates are deliberately not training labels.  A human must review the
source image and change visual_review_status before it can be used for model
training.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_positive_kg(value: object) -> float | None:
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an object_key manifest for visually reviewed single-bird scale labels.")
    parser.add_argument("--captures", required=True, type=Path, help="session_capture_metadata_*.csv")
    parser.add_argument("--media", required=True, type=Path, help="media_objects_*.csv")
    parser.add_argument("--weight-sessions", required=True, type=Path, help="weight_sessions_*.csv")
    parser.add_argument("--output", required=True, type=Path, help="Candidate manifest CSV for the image-download step.")
    parser.add_argument("--summary-output", type=Path, help="Optional JSON summary.")
    args = parser.parse_args()

    captures = read_csv(args.captures)
    media_by_session: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(args.media):
        media_by_session.setdefault(row["session_id"], []).append(row)
    weight_by_session = {row["session_id"]: row for row in read_csv(args.weight_sessions)}

    candidates: list[dict[str, object]] = []
    rejected = {"missing_weight_session": 0, "session_not_finalized": 0, "scale_not_stable": 0, "invalid_scale_weight": 0, "detection_count_not_one": 0, "missing_media": 0}
    for capture in captures:
        session_id = capture["session_id"]
        weight_session = weight_by_session.get(session_id)
        if not weight_session:
            rejected["missing_weight_session"] += 1
            continue
        if weight_session.get("status") != "finalized":
            rejected["session_not_finalized"] += 1
            continue
        try:
            metadata = json.loads(capture["raw_metadata"])
        except (KeyError, json.JSONDecodeError):
            rejected["detection_count_not_one"] += 1
            continue
        scale = metadata.get("scale") or {}
        if scale.get("weight_stable") is not True:
            rejected["scale_not_stable"] += 1
            continue
        displayed_weight_kg = as_positive_kg(scale.get("weight_kg"))
        if displayed_weight_kg is None:
            rejected["invalid_scale_weight"] += 1
            continue
        detections = metadata.get("detections") or []
        if len(detections) != 1:
            rejected["detection_count_not_one"] += 1
            continue
        matching_media = media_by_session.get(session_id, [])
        if not matching_media:
            rejected["missing_media"] += 1
            continue
        # Each capture currently emits an original JPEG followed shortly by an
        # inference-overlay JPEG.  The metadata has no explicit variant field,
        # so retain the earliest-created media object as the original image.
        # This avoids mixing the green overlay into single-bird training data.
        original_media = min(
            matching_media,
            key=lambda media: (media.get("created_at") or "9999-12-31", media.get("id") or ""),
        )
        detection = detections[0]
        roi = (metadata.get("roi") or {}).get("xyxy")
        candidates.append({
            "session_id": session_id,
            "media_id": original_media["id"],
            "bucket": original_media.get("bucket"),
            "object_key": original_media["object_key"],
            "captured_at": original_media.get("captured_at") or capture.get("occurred_at"),
            "displayed_weight_g": round(displayed_weight_kg * 1000, 3),
            "scale_resolution_g": 100,
            "weight_stable": True,
            "weight_session_status": weight_session.get("status"),
            "detector_count": 1,
            "detection_index": detection.get("detection_index"),
            "detection_pixel_x": (detection.get("pixel_xy") or [None, None])[0],
            "detection_pixel_y": (detection.get("pixel_xy") or [None, None])[1],
            "roi_xyxy": json.dumps(roi),
            "visual_review_status": "REQUIRES_VISUAL_REVIEW",
            "visually_verified_single_bird": False,
            "use_for_training": False,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "session_id", "media_id", "bucket", "object_key", "captured_at", "displayed_weight_g",
        "scale_resolution_g", "weight_stable", "weight_session_status", "detector_count",
        "detection_index", "detection_pixel_x", "detection_pixel_y", "roi_xyxy",
        "visual_review_status", "visually_verified_single_bird", "use_for_training",
    ]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidates)
    summary = {"captures_read": len(captures), "download_candidates": len(candidates), "rejected": rejected, "output": str(args.output)}
    if args.summary_output:
        args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
