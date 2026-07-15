from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_artifact_root_dir() -> str:
    return str(Path(__file__).resolve().parents[1] / "artifacts" / "weighvision")


def _default_weighvision_dataset_path() -> str:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "docs" / "iot-layer" / "evidence" / "batch2-weight-audit-dataset.csv"
        if candidate.exists():
            return str(candidate)

    return str(current.parents[1] / "artifacts" / "weighvision" / "datasets" / "batch2-weight-audit-dataset.csv")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "cloud-ml-model-service"

    host: str = "0.0.0.0"
    port: int = 5135

    log_level: str = "INFO"
    log_format: str = "json"

    database_url: str

    # RabbitMQ configuration
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672")
    rabbitmq_exchange: str = os.getenv("RABBITMQ_EXCHANGE", "farmiq.events")
    artifact_base_url: str = os.getenv("WEIGHVISION_ARTIFACT_BASE_URL", "http://cloud-ml-model-service:5135")
    artifact_root_dir: str = os.getenv(
        "WEIGHVISION_ARTIFACT_ROOT_DIR",
        _default_artifact_root_dir(),
    )
    default_weighvision_dataset_path: str = os.getenv(
        "WEIGHVISION_BASELINE_DATASET_PATH",
        _default_weighvision_dataset_path(),
    )

    testing: bool = False

    def new_id(self) -> str:
        return os.getenv("ID_PREFIX", "") + uuid4().hex
