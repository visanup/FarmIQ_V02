"""Explicit, isolated HTTP runtime for the Hybrid Trial Model 75Sx25V."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from weight_prediction.edge_runtime import EdgeWeightPredictor


router = APIRouter(prefix="/api/v1/ml/hybrid-trial", tags=["Hybrid Trial"])
PACKAGE_DIR = Path(__file__).resolve().parents[1] / "ml_weight_prediction" / "artifacts" / "hybrid-trial-75s25v-v1-edge"


class HybridTrialPredictRequest(BaseModel):
    record_id: str | None = None
    breed: str
    sex: str
    age_days: int = Field(ge=1, le=56)
    area_mm2: float
    length_mm: float
    width_mm: float
    height_mm: float
    depth_mm: float
    confidence: float = Field(ge=0, le=1)
    volume_proxy_area_height_mm3: float
    volume_proxy_lwh_mm3: float
    length_width_ratio: float
    bbox_area_px: float
    bbox_aspect_ratio: float
    mask_fill_ratio: float
    is_height_outlier: int = Field(ge=0, le=1)


@lru_cache(maxsize=1)
def predictor() -> EdgeWeightPredictor:
    return EdgeWeightPredictor(PACKAGE_DIR)


@router.get("/health")
def health() -> dict[str, Any]:
    manifest = predictor().manifest
    return {"status": "healthy", "model_version": manifest["model_version"], "prediction_mode": manifest["prediction_mode"]}


@router.post("/predict")
def predict(payload: HybridTrialPredictRequest) -> dict[str, Any]:
    result = predictor().predict(payload.model_dump())
    if result["prediction_status"].startswith("REJECTED"):
        raise HTTPException(status_code=422, detail=result)
    return result
