from __future__ import annotations

import argparse
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import yaml


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DatasetPair:
    image: Path
    label: Path | None


@dataclass(frozen=True)
class SplitDatasetPairs:
    train: list[DatasetPair]
    val: list[DatasetPair]
    test: list[DatasetPair]


@dataclass(frozen=True)
class PreparedDataset:
    dataset_yaml: Path
    task: str
    names: list[str]
    total_images: int
    source_total_images: int
    train_count: int
    val_count: int
    test_count: int
    extra_train_copies: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare flat YOLO26 dataset into train/val/test splits.")
    parser.add_argument("--src", default="Chicken Segmentation.yolo26", help="Source dataset directory")
    parser.add_argument("--dest", default="data", help="Destination directory for prepared dataset")
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--task", choices=["auto", "detect", "segment"], default="auto")
    parser.add_argument(
        "--class-map",
        default=None,
        help='Optional class remapping, e.g. "CK=CK,CK-S=NCK,NCK=NCK"',
    )
    parser.add_argument(
        "--oversample-class",
        default=None,
        help='Optional class name(s) to oversample in the train split, e.g. "CK-S" or "CK-S,NCK"',
    )
    parser.add_argument(
        "--oversample-factor",
        type=int,
        default=1,
        help="Total train copies for matching images. Example: 3 = original + 2 extra copies.",
    )
    parser.add_argument("--force", action="store_true", help="Recreate destination directory if it exists")
    return parser.parse_args()


def _resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (SCRIPT_DIR / path).resolve()


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Source data.yaml not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML object in: {path}")
    return data


def _resolve_names(config: dict) -> list[str]:
    names = config.get("names")
    if isinstance(names, list):
        return [str(item) for item in names]
    if isinstance(names, dict):
        ordered_keys = sorted(names.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value))
        return [str(names[key]) for key in ordered_keys]
    nc = config.get("nc")
    if isinstance(nc, int) and nc > 0:
        return [f"class_{index}" for index in range(nc)]
    raise ValueError("Could not resolve class names from source data.yaml")


def _parse_class_map(class_map_value: str | None, source_names: Sequence[str]) -> tuple[list[str], dict[int, int]]:
    source_names_list = [str(name) for name in source_names]
    rename_by_name: dict[str, str] = {}

    if class_map_value:
        parts = [part.strip() for part in class_map_value.split(",") if part.strip()]
        if not parts:
            raise ValueError("Class map was provided but no mappings were found.")

        for part in parts:
            if "=" not in part:
                raise ValueError(f"Invalid class map entry '{part}'. Expected OLD=NEW format.")
            source_name, target_name = (value.strip() for value in part.split("=", 1))
            if not source_name or not target_name:
                raise ValueError(f"Invalid class map entry '{part}'. Both OLD and NEW names are required.")
            if source_name not in source_names_list:
                available = ", ".join(source_names_list)
                raise ValueError(f"Unknown source class '{source_name}'. Available classes: {available}")
            rename_by_name[source_name] = target_name

    target_names: list[str] = []
    old_index_to_new_index: dict[int, int] = {}
    for old_index, source_name in enumerate(source_names_list):
        target_name = rename_by_name.get(source_name, source_name)
        if target_name not in target_names:
            target_names.append(target_name)
        old_index_to_new_index[old_index] = target_names.index(target_name)

    return target_names, old_index_to_new_index


def _parse_name_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _validate_oversample_args(oversample_class: str | None, oversample_factor: int) -> None:
    if oversample_factor < 1:
        raise ValueError(f"Oversample factor must be >= 1, got {oversample_factor}")
    if oversample_factor > 1 and not _parse_name_list(oversample_class):
        raise ValueError("Oversample factor > 1 requires --oversample-class.")


def _parse_oversample_class_ids(
    oversample_class_value: str | None,
    source_names: Sequence[str],
    target_names: Sequence[str],
    class_index_map: dict[int, int],
) -> set[int]:
    requested_names = _parse_name_list(oversample_class_value)
    if not requested_names:
        return set()

    source_names_list = [str(name) for name in source_names]
    source_name_to_index = {name: index for index, name in enumerate(source_names_list)}
    target_name_to_source_indices: dict[str, set[int]] = {}
    for old_index, source_name in enumerate(source_names_list):
        target_name = target_names[class_index_map[old_index]]
        target_name_to_source_indices.setdefault(target_name, set()).add(old_index)

    selected_source_indices: set[int] = set()
    for requested_name in requested_names:
        if requested_name in source_name_to_index:
            selected_source_indices.add(source_name_to_index[requested_name])
            continue
        if requested_name in target_name_to_source_indices:
            selected_source_indices.update(target_name_to_source_indices[requested_name])
            continue
        available_names = sorted(set(source_names_list) | set(target_names))
        raise ValueError(
            f"Unknown oversample class '{requested_name}'. Available class names: {', '.join(available_names)}"
        )

    return selected_source_indices


def _validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    ratios = [train_ratio, val_ratio, test_ratio]
    if any(ratio < 0 for ratio in ratios):
        raise ValueError("Split ratios must be non-negative")
    total = sum(ratios)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Split ratios must sum to 1.0, got {total:.6f}")


def _iter_images(images_dir: Path) -> Iterable[Path]:
    for file_path in sorted(images_dir.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
            yield file_path


def _collect_pairs_from_dirs(images_dir: Path, labels_dir: Path) -> list[DatasetPair]:
    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")
    if not labels_dir.exists():
        raise FileNotFoundError(f"Labels directory not found: {labels_dir}")

    pairs: list[DatasetPair] = []
    for image_path in _iter_images(images_dir):
        label_path = labels_dir / f"{image_path.stem}.txt"
        pairs.append(DatasetPair(image=image_path, label=label_path if label_path.exists() else None))

    if not pairs:
        raise ValueError(f"No images found in: {images_dir}")
    return pairs


def _collect_flat_pairs(src_dir: Path) -> list[DatasetPair]:
    return _collect_pairs_from_dirs(src_dir / "images", src_dir / "labels")


def _resolve_existing_dir(base_dir: Path, candidates: Sequence[str]) -> Path | None:
    for candidate in candidates:
        path = base_dir / candidate
        if path.exists() and path.is_dir():
            return path
    return None


def _has_flat_layout(src_dir: Path) -> bool:
    return (src_dir / "images").is_dir() and (src_dir / "labels").is_dir()


def _has_split_layout(src_dir: Path) -> bool:
    train_dir = _resolve_existing_dir(src_dir, ("train",))
    val_dir = _resolve_existing_dir(src_dir, ("val", "valid"))
    test_dir = _resolve_existing_dir(src_dir, ("test",))
    return bool(train_dir and val_dir and test_dir)


def _collect_split_pairs(src_dir: Path) -> SplitDatasetPairs:
    train_dir = _resolve_existing_dir(src_dir, ("train",))
    val_dir = _resolve_existing_dir(src_dir, ("val", "valid"))
    test_dir = _resolve_existing_dir(src_dir, ("test",))

    if not train_dir:
        raise FileNotFoundError(f"Split dataset train directory not found under: {src_dir}")
    if not val_dir:
        raise FileNotFoundError(f"Split dataset val/valid directory not found under: {src_dir}")
    if not test_dir:
        raise FileNotFoundError(f"Split dataset test directory not found under: {src_dir}")

    return SplitDatasetPairs(
        train=_collect_pairs_from_dirs(train_dir / "images", train_dir / "labels"),
        val=_collect_pairs_from_dirs(val_dir / "images", val_dir / "labels"),
        test=_collect_pairs_from_dirs(test_dir / "images", test_dir / "labels"),
    )


def _infer_task_from_pairs(pairs: Sequence[DatasetPair], fallback: str = "detect") -> str:
    for pair in pairs:
        if not pair.label or not pair.label.exists():
            continue
        for line in pair.label.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            part_count = len(stripped.split())
            if part_count > 5:
                return "segment"
            if part_count == 5:
                return "detect"
    return fallback


def _resolve_task(task_arg: str, pairs: Sequence[DatasetPair]) -> str:
    if task_arg != "auto":
        return task_arg
    return _infer_task_from_pairs(pairs)


def _ensure_clean_dest(dest_dir: Path, force: bool) -> None:
    if dest_dir.exists() and force:
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)


def _split_counts(total: int, train_ratio: float, val_ratio: float) -> tuple[int, int, int]:
    train_count = int(total * train_ratio)
    val_count = int(total * val_ratio)
    test_count = total - train_count - val_count
    if total >= 3:
        if train_count == 0:
            train_count = 1
            test_count -= 1
        if val_count == 0:
            val_count = 1
            test_count -= 1
        if test_count < 0:
            raise ValueError("Split ratios produce invalid counts for this dataset size")
    return train_count, val_count, test_count


def _remap_label_line(line: str, class_index_map: dict[int, int]) -> str:
    stripped = line.strip()
    if not stripped:
        return ""

    parts = stripped.split()
    try:
        old_class_index = int(float(parts[0]))
    except ValueError as exc:
        raise ValueError(f"Invalid class index in label line: {line!r}") from exc

    if old_class_index not in class_index_map:
        raise ValueError(f"Label class index {old_class_index} was not found in class map.")

    parts[0] = str(class_index_map[old_class_index])
    return " ".join(parts)


def _extract_label_class_ids(pair: DatasetPair) -> set[int]:
    if not pair.label or not pair.label.exists():
        return set()

    class_ids: set[int] = set()
    for line in pair.label.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        try:
            class_ids.add(int(float(parts[0])))
        except ValueError as exc:
            raise ValueError(f"Invalid class index in label line: {line!r}") from exc
    return class_ids


def _pair_matches_oversample(pair: DatasetPair, oversample_class_ids: set[int]) -> bool:
    return bool(oversample_class_ids and (_extract_label_class_ids(pair) & oversample_class_ids))


def _copy_pair(
    pair: DatasetPair,
    image_dest: Path,
    label_dest: Path,
    class_index_map: dict[int, int],
    name_suffix: str = "",
) -> None:
    output_image = image_dest / f"{pair.image.stem}{name_suffix}{pair.image.suffix}"
    shutil.copy2(pair.image, output_image)
    output_label = label_dest / f"{pair.image.stem}{name_suffix}.txt"
    if pair.label and pair.label.exists():
        remapped_lines = [
            _remap_label_line(line, class_index_map)
            for line in pair.label.read_text(encoding="utf-8").splitlines()
        ]
        output_text = "\n".join(line for line in remapped_lines if line.strip())
        if output_text:
            output_text += "\n"
        output_label.write_text(output_text, encoding="utf-8")
    else:
        output_label.write_text("", encoding="utf-8")


def _copy_split_pairs(
    split_name: str,
    split_pairs: Sequence[DatasetPair],
    image_dest: Path,
    label_dest: Path,
    class_index_map: dict[int, int],
    oversample_class_ids: set[int],
    oversample_factor: int,
) -> tuple[int, int]:
    output_count = 0
    extra_train_copies = 0

    for pair in split_pairs:
        _copy_pair(pair, image_dest, label_dest, class_index_map)
        output_count += 1

        if split_name != "train":
            continue
        if not _pair_matches_oversample(pair, oversample_class_ids):
            continue

        for duplicate_index in range(1, oversample_factor):
            _copy_pair(
                pair,
                image_dest,
                label_dest,
                class_index_map,
                name_suffix=f"__os{duplicate_index}",
            )
            output_count += 1
            extra_train_copies += 1

    return output_count, extra_train_copies


def _write_dataset_yaml(dest_dir: Path, task: str, names: list[str]) -> Path:
    dataset_yaml = dest_dir / "dataset.yaml"
    payload = {
        "path": str(dest_dir.resolve().as_posix()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "task": task,
        "nc": len(names),
        "names": names,
    }
    dataset_yaml.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return dataset_yaml


def prepare_dataset(
    src_dir: Path,
    dest_dir: Path,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
    seed: int = 42,
    task_arg: str = "auto",
    class_map: str | None = None,
    oversample_class: str | None = None,
    oversample_factor: int = 1,
    force: bool = False,
) -> PreparedDataset:
    _validate_ratios(train_ratio, val_ratio, test_ratio)
    _validate_oversample_args(oversample_class, oversample_factor)

    source_yaml = _load_yaml(src_dir / "data.yaml")
    source_names = _resolve_names(source_yaml)
    names, class_index_map = _parse_class_map(class_map, source_names)
    oversample_class_ids = _parse_oversample_class_ids(oversample_class, source_names, names, class_index_map)
    if _has_flat_layout(src_dir):
        pairs = _collect_flat_pairs(src_dir)
        task = _resolve_task(task_arg, pairs)

        randomizer = random.Random(seed)
        shuffled_pairs = list(pairs)
        randomizer.shuffle(shuffled_pairs)

        train_count, val_count, test_count = _split_counts(len(shuffled_pairs), train_ratio, val_ratio)
        train_pairs = shuffled_pairs[:train_count]
        val_pairs = shuffled_pairs[train_count:train_count + val_count]
        test_pairs = shuffled_pairs[train_count + val_count:]
        total_images = len(shuffled_pairs)
    elif _has_split_layout(src_dir):
        split_pairs = _collect_split_pairs(src_dir)
        combined_pairs = [*split_pairs.train, *split_pairs.val, *split_pairs.test]
        task = _resolve_task(task_arg, combined_pairs)
        train_pairs = split_pairs.train
        val_pairs = split_pairs.val
        test_pairs = split_pairs.test
        total_images = len(combined_pairs)
    else:
        raise FileNotFoundError(
            "Dataset layout not recognized. Expected either a flat export with "
            "'images/' + 'labels/' or a split export with 'train/', 'val|valid/', 'test/'."
        )

    source_total_images = total_images
    _ensure_clean_dest(dest_dir, force)

    split_counts: dict[str, int] = {}
    extra_train_copies = 0
    for split_name, split_pairs in (
        ("train", train_pairs),
        ("val", val_pairs),
        ("test", test_pairs),
    ):
        image_dest = dest_dir / "images" / split_name
        label_dest = dest_dir / "labels" / split_name
        image_dest.mkdir(parents=True, exist_ok=True)
        label_dest.mkdir(parents=True, exist_ok=True)
        copied_count, split_extra_train_copies = _copy_split_pairs(
            split_name=split_name,
            split_pairs=split_pairs,
            image_dest=image_dest,
            label_dest=label_dest,
            class_index_map=class_index_map,
            oversample_class_ids=oversample_class_ids,
            oversample_factor=oversample_factor,
        )
        split_counts[split_name] = copied_count
        extra_train_copies += split_extra_train_copies

    dataset_yaml = _write_dataset_yaml(dest_dir, task, names)

    return PreparedDataset(
        dataset_yaml=dataset_yaml,
        task=task,
        names=names,
        total_images=sum(split_counts.values()),
        source_total_images=source_total_images,
        train_count=split_counts["train"],
        val_count=split_counts["val"],
        test_count=split_counts["test"],
        extra_train_copies=extra_train_copies,
    )


def main() -> int:
    args = _parse_args()
    result = prepare_dataset(
        src_dir=_resolve_local_path(args.src),
        dest_dir=_resolve_local_path(args.dest),
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
        task_arg=args.task,
        class_map=args.class_map,
        oversample_class=args.oversample_class,
        oversample_factor=args.oversample_factor,
        force=args.force,
    )
    print(f"Prepared dataset: {result.dataset_yaml}")
    print(f"Task: {result.task}")
    print(f"Classes: {', '.join(result.names)}")
    print(
        f"Images: total={result.total_images}, train={result.train_count}, "
        f"val={result.val_count}, test={result.test_count}"
    )
    if result.extra_train_copies:
        print(
            f"Oversampling: source_total={result.source_total_images}, "
            f"extra_train_copies={result.extra_train_copies}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
