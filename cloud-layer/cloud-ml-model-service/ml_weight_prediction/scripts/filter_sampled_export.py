"""Filter FarmIQ metadata to only the images selected for ML review."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def find_export(metadata_dir: Path, prefix: str) -> Path:
    matches = sorted(metadata_dir.glob(f"{prefix}_*.csv"))
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one {prefix}_*.csv in {metadata_dir}; found {len(matches)}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter metadata to sampled image files without changing raw exports.")
    parser.add_argument("--images-dir", required=True, type=Path)
    parser.add_argument("--metadata-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    image_files = sorted(path for path in args.images_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    image_stems = {path.stem for path in image_files}
    files = {name: find_export(args.metadata_dir, name) for name in ("media_objects", "session_capture_metadata", "weight_sessions", "inference_results")}

    media = read_csv(files["media_objects"])
    sampled_media = [row for row in media if Path(row["object_key"]).stem in image_stems]
    media_by_stem = {Path(row["object_key"]).stem: row for row in sampled_media}
    selected_media_ids = {row["id"] for row in sampled_media}
    selected_session_ids = {row["session_id"] for row in sampled_media}

    captures = read_csv(files["session_capture_metadata"])
    selected_captures = [row for row in captures if row["session_id"] in selected_session_ids]
    weight_sessions = read_csv(files["weight_sessions"])
    selected_weight_sessions = [row for row in weight_sessions if row["session_id"] in selected_session_ids]
    inferences = read_csv(files["inference_results"])
    selected_inferences = [row for row in inferences if row["media_id"] in selected_media_ids]

    capture_by_session = {row["session_id"]: row for row in selected_captures}
    weight_by_session = {row["session_id"]: row for row in selected_weight_sessions}
    inference_counts = Counter(row["media_id"] for row in selected_inferences)
    audit: list[dict[str, Any]] = []
    for image_path in image_files:
        media_row = media_by_stem.get(image_path.stem)
        session_id = media_row["session_id"] if media_row else ""
        audit.append(
            {
                "image_date_directory": image_path.parent.name,
                "image_filename": image_path.name,
                "image_stem": image_path.stem,
                "image_path": str(image_path),
                "media_id": media_row["id"] if media_row else "",
                "media_object_key": media_row["object_key"] if media_row else "",
                "session_id": session_id,
                "media_object_found": bool(media_row),
                "capture_metadata_found": session_id in capture_by_session,
                "weight_session_found": session_id in weight_by_session,
                "inference_result_count": inference_counts[media_row["id"]] if media_row else 0,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "sampled_media_objects.csv", sampled_media, list(media[0]))
    write_csv(args.output_dir / "sampled_session_capture_metadata.csv", selected_captures, list(captures[0]))
    write_csv(args.output_dir / "sampled_weight_sessions.csv", selected_weight_sessions, list(weight_sessions[0]))
    write_csv(args.output_dir / "sampled_inference_results.csv", selected_inferences, list(inferences[0]))
    write_csv(args.output_dir / "sampled_image_metadata_audit.csv", audit, list(audit[0]))
    summary = {
        "image_files": len(image_files),
        "sampled_media_objects": len(sampled_media),
        "sampled_sessions": len(selected_session_ids),
        "sampled_capture_metadata_rows": len(selected_captures),
        "sampled_weight_session_rows": len(selected_weight_sessions),
        "sampled_inference_rows": len(selected_inferences),
        "images_without_media_object": sum(not row["media_object_found"] for row in audit),
        "images_without_capture_metadata": sum(not row["capture_metadata_found"] for row in audit),
        "images_without_weight_session": sum(not row["weight_session_found"] for row in audit),
        "images_without_inference_result": sum(row["inference_result_count"] == 0 for row in audit),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
