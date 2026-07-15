from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelProfile:
    model_id: str
    path: Path
    family: str = "ultralytics-seg"
    conf: float | None = None
    iou: float | None = None
    imgsz: int | None = None
    device: str | None = None
    notes: str | None = None
    source: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


def camera_config_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "camera-config"


def default_model_path() -> Path:
    return camera_config_dir() / "model" / "best.pt"


def default_model_config_path() -> Path:
    return camera_config_dir() / "model" / "runtime-config.yaml"


def load_runtime_config(config_path: Path | None = None) -> dict[str, Any]:
    resolved_path = config_path or default_model_config_path()
    if not resolved_path.exists():
        return {}
    raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def list_model_profiles(config_path: Path | None = None) -> list[ModelProfile]:
    resolved_path = config_path or default_model_config_path()
    config = load_runtime_config(resolved_path)
    models = config.get("models", {})
    if not isinstance(models, dict):
        return []

    profiles: list[ModelProfile] = []
    for model_id, payload in models.items():
        if not isinstance(payload, dict):
            continue
        path_value = payload.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            continue
        model_path = (resolved_path.parent / path_value).resolve()
        profiles.append(
            ModelProfile(
                model_id=model_id,
                path=model_path,
                family=str(payload.get("family", "ultralytics-seg")),
                conf=_maybe_float(payload.get("conf")),
                iou=_maybe_float(payload.get("iou")),
                imgsz=_maybe_int(payload.get("imgsz")),
                device=_maybe_str(payload.get("device")),
                notes=_maybe_str(payload.get("notes")),
                source="config",
                metadata={"config_path": str(resolved_path)},
            )
        )
    return profiles


def resolve_model_profile(
    model: str | None = None,
    model_id: str | None = None,
    model_config: str | Path | None = None,
) -> ModelProfile:
    config_path = Path(model_config).resolve() if model_config else default_model_config_path()

    if model:
        explicit_path = Path(model).expanduser().resolve()
        if not explicit_path.exists():
            raise FileNotFoundError(f"Model weights file not found: {explicit_path}")
        return ModelProfile(
            model_id=model_id or explicit_path.stem,
            path=explicit_path,
            source="explicit",
            metadata={"config_path": str(config_path)},
        )

    profiles = {profile.model_id: profile for profile in list_model_profiles(config_path)}
    config = load_runtime_config(config_path)
    requested_model_id = model_id or _maybe_str(config.get("active_model"))

    if requested_model_id:
        profile = profiles.get(requested_model_id)
        if profile is None:
            raise KeyError(
                f"Model profile '{requested_model_id}' not found in {config_path}"
            )
        return profile

    fallback_path = default_model_path()
    if not fallback_path.exists():
        raise FileNotFoundError(
            "Model .pt not found. Provide --model or configure camera-config/model/runtime-config.yaml"
        )
    return ModelProfile(
        model_id="default_best_pt",
        path=fallback_path.resolve(),
        source="fallback",
        metadata={"config_path": str(config_path)},
    )


def resolve_fallback_profile(model_config: str | Path | None = None) -> ModelProfile | None:
    config_path = Path(model_config).resolve() if model_config else default_model_config_path()
    requested_model_id = _resolve_configured_model_id("fallback_model", config_path)
    if not requested_model_id:
        return None
    profiles = {profile.model_id: profile for profile in list_model_profiles(config_path)}
    profile = profiles.get(requested_model_id)
    if profile is None:
        raise KeyError(f"Model profile '{requested_model_id}' not found in {config_path}")
    return profile


def resolve_setting(
    cli_value: float | int | str | None,
    profile_value: float | int | str | None,
    fallback_value: float | int | str | None,
):
    if cli_value is not None:
        return cli_value
    if profile_value is not None:
        return profile_value
    return fallback_value


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _maybe_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_configured_model_id(config_key: str, config_path: Path) -> str | None:
    config = load_runtime_config(config_path)
    return _maybe_str(config.get(config_key))
