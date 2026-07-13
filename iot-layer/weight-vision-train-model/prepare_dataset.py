from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageOps


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PIL_IMAGE_FORMATS = {"jpg", "jpeg", "png", "bmp", "webp"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare YOLO dataset splits from flat images/labels source folders."
    )
    parser.add_argument(
        "--src",
        default=r"D:\FarmIQ_V02\iot-layer\weight-vision-train-model\dataset_src",
        help="Source dataset root containing images/ and labels/ folders",
    )
    parser.add_argument(
        "--dest",
        default="data",
        help="Destination dataset root to create images/{train,val,test} and labels/{train,val,test}",
    )
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train split ratio")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation split ratio")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="Test split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--force", action="store_true", help="Delete existing destination split folders first")
    parser.add_argument("--skip-cache", action="store_true", help="Skip creating Ultralytics *.cache files")
    return parser.parse_args()


def _read_classes(classes_path: Path) -> list[str]:
    if not classes_path.exists():
        raise FileNotFoundError(f"classes.txt not found: {classes_path}")
    classes = [line.strip() for line in classes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not classes:
        raise ValueError(f"No classes found in {classes_path}")
    return classes


def _collect_pairs(images_dir: Path, labels_dir: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for image_path in sorted(images_dir.iterdir()):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        label_path = labels_dir / f"{image_path.stem}.txt"
        if not label_path.exists():
            raise FileNotFoundError(f"Missing label for image {image_path.name}: {label_path}")
        pairs.append((image_path, label_path))

    if not pairs:
        raise ValueError(f"No image/label pairs found under {images_dir} and {labels_dir}")
    return pairs


def _ensure_clean_split_dirs(dest_root: Path, force: bool) -> None:
    split_dirs = [
        dest_root / "images" / split for split in ("train", "val", "test")
    ] + [
        dest_root / "labels" / split for split in ("train", "val", "test")
    ]

    if force:
        for path in split_dirs:
            if path.exists():
                shutil.rmtree(path)

    for path in split_dirs:
        path.mkdir(parents=True, exist_ok=True)


def _slice_pairs(
    pairs: list[tuple[Path, Path]], train_ratio: float, val_ratio: float, test_ratio: float
) -> dict[str, list[tuple[Path, Path]]]:
    total_ratio = train_ratio + val_ratio + test_ratio
    if abs(total_ratio - 1.0) > 1e-9:
        raise ValueError(f"Split ratios must sum to 1.0, got {total_ratio}")

    total = len(pairs)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)

    train_pairs = pairs[:train_end]
    val_pairs = pairs[train_end:val_end]
    test_pairs = pairs[val_end:]

    if not train_pairs or not val_pairs or not test_pairs:
        raise ValueError(
            f"Invalid split sizes from {total} samples: "
            f"train={len(train_pairs)}, val={len(val_pairs)}, test={len(test_pairs)}"
        )

    return {"train": train_pairs, "val": val_pairs, "test": test_pairs}


def _copy_pairs(dest_root: Path, split_name: str, pairs: Iterable[tuple[Path, Path]]) -> int:
    count = 0
    for image_path, label_path in pairs:
        shutil.copy2(image_path, dest_root / "images" / split_name / image_path.name)
        shutil.copy2(label_path, dest_root / "labels" / split_name / label_path.name)
        count += 1
    return count


def _write_dataset_yaml(dest_root: Path, classes: list[str]) -> Path:
    dataset_yaml = dest_root / "dataset.yaml"
    names_lines = "\n".join(f"  {index}: {name}" for index, name in enumerate(classes))
    dataset_yaml.write_text(
        "\n".join(
            [
                f"path: {dest_root.as_posix()}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "",
                "task: segment",
                f"nc: {len(classes)}",
                "names:",
                names_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return dataset_yaml


def _exif_size(image: Image.Image) -> tuple[int, int]:
    size = image.size
    if image.format == "JPEG":
        try:
            if exif := image.getexif():
                rotation = exif.get(274, None)
                if rotation in {6, 8}:
                    size = size[1], size[0]
        except Exception:
            pass
    return size


def _segments_to_box(segment: np.ndarray) -> np.ndarray:
    x_coords = segment[:, 0]
    y_coords = segment[:, 1]
    x_min = float(x_coords.min())
    x_max = float(x_coords.max())
    y_min = float(y_coords.min())
    y_max = float(y_coords.max())
    return np.array(
        [[(x_min + x_max) / 2.0, (y_min + y_max) / 2.0, x_max - x_min, y_max - y_min]],
        dtype=np.float32,
    )


def _verify_image_label(im_file: Path, lb_file: Path, num_classes: int) -> tuple[str, np.ndarray, tuple[int, int], list[np.ndarray]]:
    image = Image.open(im_file)
    image.verify()
    shape = _exif_size(image)
    shape = (shape[1], shape[0])
    assert shape[0] > 9 and shape[1] > 9, f"image size {shape} < 10 pixels"
    assert image.format and image.format.lower() in PIL_IMAGE_FORMATS, f"invalid image format {image.format}"
    if image.format.lower() in {"jpg", "jpeg"}:
        with im_file.open("rb") as handle:
            handle.seek(-2, 2)
            if handle.read() != b"\xff\xd9":
                ImageOps.exif_transpose(Image.open(im_file)).save(im_file, "JPEG", subsampling=0, quality=100)

    if not lb_file.exists():
        return str(im_file), np.zeros((0, 5), dtype=np.float32), shape, []

    rows = [line.split() for line in lb_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return str(im_file), np.zeros((0, 5), dtype=np.float32), shape, []

    segments = [np.array(row[1:], dtype=np.float32).reshape(-1, 2) for row in rows]
    classes = np.array([row[0] for row in rows], dtype=np.float32).reshape(-1, 1)
    boxes = np.concatenate([_segments_to_box(segment) for segment in segments], axis=0)
    labels = np.concatenate((classes, boxes), axis=1)

    points = np.concatenate([segment.reshape(-1, 2) for segment in segments], axis=0)
    assert points.max() <= 1.01, f"non-normalized or out of bounds coordinates in {lb_file.name}"
    assert labels.min() >= -0.01, f"negative class labels or coordinate in {lb_file.name}"
    max_cls = int(labels[:, 0].max()) if len(labels) else 0
    assert max_cls < num_classes, f"class {max_cls} exceeds class count {num_classes}"
    return str(im_file), labels.astype(np.float32), shape, segments


def _build_split_cache(dest_root: Path, split_name: str, num_classes: int) -> Path:
    image_dir = dest_root / "images" / split_name
    label_dir = dest_root / "labels" / split_name
    cache_path = label_dir.with_suffix(".cache")
    image_files = sorted(path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    label_files = [label_dir / f"{path.stem}.txt" for path in image_files]

    labels = []
    missing = empty = corrupt = found = 0
    for image_path, label_path in zip(image_files, label_files):
        try:
            im_file, lb, shape, segments = _verify_image_label(image_path, label_path, num_classes)
            labels.append(
                {
                    "im_file": im_file,
                    "shape": shape,
                    "cls": lb[:, 0:1],
                    "bboxes": lb[:, 1:],
                    "segments": segments,
                    "keypoints": None,
                    "normalized": True,
                    "bbox_format": "xywh",
                }
            )
            if label_path.exists():
                if len(lb):
                    found += 1
                else:
                    empty += 1
            else:
                missing += 1
        except Exception as exc:
            corrupt += 1
            print(f"[WARN] Corrupt pair ignored for cache: {image_path.name} ({exc})")

    from ultralytics.data.dataset import DATASET_CACHE_VERSION
    from ultralytics.data.utils import get_hash, save_dataset_cache_file

    cache_payload = {
        "labels": labels,
        "hash": get_hash([str(path) for path in label_files + image_files]),
        "results": (found, missing, empty, corrupt, len(image_files)),
        "msgs": [],
    }
    save_dataset_cache_file("", cache_path, cache_payload, DATASET_CACHE_VERSION)
    return cache_path


def main() -> int:
    args = _parse_args()
    src_root = Path(args.src)
    dest_root = Path(args.dest)

    images_dir = src_root / "images"
    labels_dir = src_root / "labels"
    if not images_dir.exists() or not labels_dir.exists():
        raise FileNotFoundError(f"Expected images/ and labels/ in source dataset root: {src_root}")

    classes = _read_classes(src_root / "classes.txt")
    pairs = _collect_pairs(images_dir, labels_dir)

    rng = random.Random(args.seed)
    rng.shuffle(pairs)

    _ensure_clean_split_dirs(dest_root, force=args.force)
    split_pairs = _slice_pairs(pairs, args.train_ratio, args.val_ratio, args.test_ratio)

    print(f"Source pairs: {len(pairs)}")
    for split_name, split_items in split_pairs.items():
        copied = _copy_pairs(dest_root, split_name, split_items)
        print(f"- {split_name}: {copied}")

    dataset_yaml = _write_dataset_yaml(dest_root, classes)
    print(f"Generated dataset config: {dataset_yaml}")
    if not args.skip_cache:
        for split_name in ("train", "val", "test"):
            cache_path = _build_split_cache(dest_root, split_name, len(classes))
            print(f"Generated cache: {cache_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
