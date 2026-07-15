from __future__ import annotations

import csv
import hashlib
import json
import math
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from app.schemas import WeighVisionDatasetContractResponse


@dataclass
class DatasetRow:
    timestamp: datetime
    target_weight_kg: float
    features: dict[str, float]
    raw: dict[str, Any]


@dataclass
class TrainingArtifacts:
    feature_names: list[str]
    dataset_rows: int
    training_rows: int
    validation_rows: int
    dropped_rows: int
    train_metrics: dict[str, float]
    validation_metrics: dict[str, float]
    naive_metrics: dict[str, float]
    model_payload: dict[str, Any]
    package_dir: Path
    package_file: Path
    checksum_sha256: str
    generated_at: datetime


FEATURE_COLUMNS = [
    "selected_area_mm2",
    "selected_confidence",
    "selected_depth_mm",
    "selected_height_mm",
    "selected_width_mm",
    "selected_length_mm",
    "floor_depth_mm",
    "roi_count",
    "detection_count",
]


def parse_dataset_rows(dataset_path: Path) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    with dataset_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            timestamp_raw = raw_row.get("timestamp")
            target_raw = raw_row.get("weight_kg")
            if not timestamp_raw or not target_raw:
                continue

            try:
                timestamp = datetime.fromisoformat(timestamp_raw)
            except ValueError:
                continue

            target_weight_kg = _to_float(target_raw)
            if target_weight_kg is None or target_weight_kg <= 0:
                continue

            features: dict[str, float] = {}
            valid = True
            for column in FEATURE_COLUMNS:
                value = _to_float(raw_row.get(column))
                if value is None or not math.isfinite(value):
                    valid = False
                    break
                features[column] = value

            if not valid:
                continue

            rows.append(
                DatasetRow(
                    timestamp=timestamp,
                    target_weight_kg=target_weight_kg,
                    features=features,
                    raw=raw_row,
                )
            )

    rows.sort(key=lambda row: row.timestamp)
    return rows


def train_and_package_baseline(
    *,
    dataset_path: Path,
    package_version: str,
    output_root: Path,
    contract: WeighVisionDatasetContractResponse,
) -> TrainingArtifacts:
    dataset_rows = parse_dataset_rows(dataset_path)
    if len(dataset_rows) < 8:
        raise ValueError("Not enough valid dataset rows to train baseline model")

    split_index = max(1, min(len(dataset_rows) - 1, math.floor(len(dataset_rows) * 0.8)))
    train_rows = dataset_rows[:split_index]
    validation_rows = dataset_rows[split_index:]
    if not validation_rows:
        validation_rows = train_rows[-1:]
        train_rows = train_rows[:-1]

    feature_names = FEATURE_COLUMNS[:]
    means, stds = compute_scaler(train_rows, feature_names)
    coefficients, intercept = fit_linear_regression(train_rows, feature_names, means, stds)

    train_metrics = evaluate_model(train_rows, feature_names, means, stds, coefficients, intercept)
    validation_metrics = evaluate_model(validation_rows, feature_names, means, stds, coefficients, intercept)
    naive_value = sum(row.target_weight_kg for row in train_rows) / len(train_rows)
    naive_metrics = evaluate_naive(validation_rows, naive_value)

    generated_at = datetime.now(tz=timezone.utc)
    model_payload = {
        "model_type": "linear_regression",
        "feature_order": feature_names,
        "feature_means": means,
        "feature_stds": stds,
        "coefficients": coefficients,
        "intercept": intercept,
        "trained_at": generated_at.isoformat(),
        "dataset_path": str(dataset_path),
        "dataset_rows": len(dataset_rows),
        "training_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "train_metrics": train_metrics,
        "validation_metrics": validation_metrics,
        "naive_metrics": naive_metrics,
    }

    package_dir = output_root / package_version
    if package_dir.exists():
        for existing in package_dir.rglob("*"):
            if existing.is_file():
                existing.unlink()
        for existing_dir in sorted(
            [path for path in package_dir.rglob("*") if path.is_dir()],
            reverse=True,
        ):
            existing_dir.rmdir()
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "model").mkdir(exist_ok=True)
    (package_dir / "schema").mkdir(exist_ok=True)
    (package_dir / "evidence").mkdir(exist_ok=True)

    model_path = package_dir / "model" / "model.json"
    model_path.write_text(json.dumps(model_payload, indent=2), encoding="utf-8")
    (package_dir / "schema" / "feature-schema.json").write_text(
        json.dumps(contract.model_dump(), indent=2, default=str),
        encoding="utf-8",
    )
    (package_dir / "evidence" / "metrics-summary.json").write_text(
        json.dumps(
            {
                "training_rows": len(train_rows),
                "validation_rows": len(validation_rows),
                "train_metrics": train_metrics,
                "validation_metrics": validation_metrics,
                "naive_metrics": naive_metrics,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    manifest_payload = {
        "packageVersion": package_version,
        "modelFamily": "weighvision-weight-predictor",
        "runtimeFamily": "python-linear-regression",
        "runtimeVersion": "1.0.0",
        "featureSchemaVersion": contract.featureSchemaVersion,
        "entrypoint": "model/model.json",
        "channel": "stable",
        "metadata": {
            "model_version": package_version,
            "algorithm": "linear_regression",
            "dataset_rows": len(dataset_rows),
            "training_rows": len(train_rows),
            "validation_rows": len(validation_rows),
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "naive_metrics": naive_metrics,
            "shadow_mode_only": True,
        },
    }
    manifest_path = package_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    package_file = output_root / f"{package_version}.tar.gz"
    if package_file.exists():
        package_file.unlink()

    with tarfile.open(package_file, "w:gz") as tar:
        tar.add(package_dir, arcname=package_version)

    checksum_sha256 = hashlib.sha256(package_file.read_bytes()).hexdigest()

    return TrainingArtifacts(
        feature_names=feature_names,
        dataset_rows=len(dataset_rows),
        training_rows=len(train_rows),
        validation_rows=len(validation_rows),
        dropped_rows=0,
        train_metrics=train_metrics,
        validation_metrics=validation_metrics,
        naive_metrics=naive_metrics,
        model_payload=model_payload,
        package_dir=package_dir,
        package_file=package_file,
        checksum_sha256=checksum_sha256,
        generated_at=generated_at,
    )


def compute_scaler(rows: Iterable[DatasetRow], feature_names: list[str]) -> tuple[list[float], list[float]]:
    means: list[float] = []
    stds: list[float] = []
    row_list = list(rows)
    for feature_name in feature_names:
        values = [row.features[feature_name] for row in row_list]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 1.0
        means.append(mean)
        stds.append(std)
    return means, stds


def fit_linear_regression(
    rows: list[DatasetRow],
    feature_names: list[str],
    means: list[float],
    stds: list[float],
    ridge_lambda: float = 1e-6,
) -> tuple[list[float], float]:
    design_matrix: list[list[float]] = []
    targets: list[float] = []
    for row in rows:
        scaled = scale_row(row.features, feature_names, means, stds)
        design_matrix.append([1.0, *scaled])
        targets.append(row.target_weight_kg)

    xtx = multiply_transpose(design_matrix)
    for idx in range(1, len(xtx)):
        xtx[idx][idx] += ridge_lambda
    xty = multiply_transpose_vector(design_matrix, targets)
    solution = solve_linear_system(xtx, xty)
    intercept = solution[0]
    coefficients = solution[1:]
    return coefficients, intercept


def evaluate_model(
    rows: list[DatasetRow],
    feature_names: list[str],
    means: list[float],
    stds: list[float],
    coefficients: list[float],
    intercept: float,
) -> dict[str, float]:
    predictions = [
        predict_weight(row.features, feature_names, means, stds, coefficients, intercept)
        for row in rows
    ]
    targets = [row.target_weight_kg for row in rows]
    return compute_metrics(targets, predictions)


def evaluate_naive(rows: list[DatasetRow], naive_prediction: float) -> dict[str, float]:
    targets = [row.target_weight_kg for row in rows]
    predictions = [naive_prediction for _ in rows]
    return compute_metrics(targets, predictions)


def predict_weight(
    features: dict[str, float],
    feature_names: list[str],
    means: list[float],
    stds: list[float],
    coefficients: list[float],
    intercept: float,
) -> float:
    scaled = scale_row(features, feature_names, means, stds)
    return intercept + sum(coefficient * value for coefficient, value in zip(coefficients, scaled))


def scale_row(
    features: dict[str, float],
    feature_names: list[str],
    means: list[float],
    stds: list[float],
) -> list[float]:
    scaled: list[float] = []
    for index, feature_name in enumerate(feature_names):
        std = stds[index] or 1.0
        scaled.append((features[feature_name] - means[index]) / std)
    return scaled


def compute_metrics(targets: list[float], predictions: list[float]) -> dict[str, float]:
    count = len(targets)
    mae = sum(abs(target - prediction) for target, prediction in zip(targets, predictions)) / count
    rmse = math.sqrt(
        sum((target - prediction) ** 2 for target, prediction in zip(targets, predictions)) / count
    )
    target_mean = sum(targets) / count
    ss_tot = sum((target - target_mean) ** 2 for target in targets)
    ss_res = sum((target - prediction) ** 2 for target, prediction in zip(targets, predictions))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return {
        "mae_kg": round(mae, 6),
        "rmse_kg": round(rmse, 6),
        "r2": round(r2, 6),
    }


def multiply_transpose(matrix: list[list[float]]) -> list[list[float]]:
    width = len(matrix[0])
    result = [[0.0 for _ in range(width)] for _ in range(width)]
    for row in matrix:
        for i in range(width):
            for j in range(width):
                result[i][j] += row[i] * row[j]
    return result


def multiply_transpose_vector(matrix: list[list[float]], vector: list[float]) -> list[float]:
    width = len(matrix[0])
    result = [0.0 for _ in range(width)]
    for row, target in zip(matrix, vector):
        for i in range(width):
            result[i] += row[i] * target
    return result


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [vector[idx]] for idx, row in enumerate(matrix)]

    for col in range(size):
        pivot = max(range(col, size), key=lambda row_index: abs(augmented[row_index][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            raise ValueError("Singular matrix encountered during baseline training")
        if pivot != col:
            augmented[col], augmented[pivot] = augmented[pivot], augmented[col]

        pivot_value = augmented[col][col]
        for j in range(col, size + 1):
            augmented[col][j] /= pivot_value

        for row_index in range(size):
            if row_index == col:
                continue
            factor = augmented[row_index][col]
            for j in range(col, size + 1):
                augmented[row_index][j] -= factor * augmented[col][j]

    return [augmented[idx][size] for idx in range(size)]


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(float(value)):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return None
    if math.isnan(numeric):
        return None
    return numeric
