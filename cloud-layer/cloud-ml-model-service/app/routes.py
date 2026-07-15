from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import Settings
from app.db import InMemoryMlModelDb, MlModelDb
from app.schemas import (
    DeploymentConfig,
    DeploymentCreate,
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentStatus,
    DeploymentUpdate,
    ListMeta,
    ModelCreate,
    ModelHyperparameter,
    ModelListResponse,
    ModelMetadata,
    ModelMetric,
    ModelResponse,
    ModelStatus,
    ModelType,
    ModelUpdate,
    TrainingRequest,
    TrainingResponse,
    WeighVisionBaselineBootstrapResponse,
    WeighVisionBaselineTrainingRequest,
    WeighVisionBaselineTrainingResponse,
    WeighVisionDatasetContractResponse,
    WeighVisionModelPackageCreate,
    WeighVisionModelPackageListResponse,
    WeighVisionModelPackageResponse,
    WeighVisionPackageManifest,
    WeighVisionSiteSubscriptionAckRequest,
    WeighVisionSiteSubscriptionAckResponse,
    WeighVisionSiteSubscriptionResolveResponse,
    WeighVisionSiteSubscriptionResponse,
    WeighVisionSiteSubscriptionUpsert,
    WeighVisionDatasetField,
)
from app.weighvision_baseline import train_and_package_baseline

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()


def dataset_contract_payload() -> WeighVisionDatasetContractResponse:
    entity_keys = [
        WeighVisionDatasetField(
            name="tenant_id",
            role="entity",
            dataType="string",
            required=True,
            source="edge sync payload",
            description="Tenant scope for subscription, training, and prediction partitioning.",
        ),
        WeighVisionDatasetField(
            name="session_id",
            role="entity",
            dataType="string",
            required=True,
            source="edge-weighvision-session.weight_sessions.id",
            description="Canonical session identifier for one weighvision event stream.",
        ),
        WeighVisionDatasetField(
            name="capture_id",
            role="entity",
            dataType="string",
            required=True,
            source="weight-vision-capture metadata.image_id",
            description="Capture identifier for one image and metadata bundle.",
        ),
    ]
    feature_fields = [
        ("selected_area_mm2", "edge normalized feature mapping", "Selected-object area in square millimeters."),
        ("selected_mask_area_px2", "edge normalized feature mapping", "Selected-object mask area in square pixels."),
        ("selected_bbox_width_px", "edge normalized feature mapping", "Bounding-box width in pixels."),
        ("selected_bbox_height_px", "edge normalized feature mapping", "Bounding-box height in pixels."),
        ("selected_width_mm", "edge normalized feature mapping", "Estimated body width in millimeters."),
        ("selected_length_mm", "edge normalized feature mapping", "Estimated body length in millimeters."),
        ("selected_height_mm", "edge normalized feature mapping", "Estimated body height in millimeters."),
        ("selected_depth_mm", "edge normalized feature mapping", "Selected-object depth from stereo geometry."),
        ("selected_confidence", "edge normalized feature mapping", "Segmentation confidence score."),
        ("camera_focal_length_px", "capture metadata camera.focal_length_px", "Stereo focal length in pixels."),
        ("camera_baseline_mm", "capture metadata camera.baseline_mm", "Stereo baseline in millimeters."),
    ]
    context_fields = [
        ("farm_id", "edge/cloud tenant topology", "Farm identifier."),
        ("barn_id", "edge/cloud tenant topology", "Barn identifier."),
        ("station_id", "weight-vision-service station binding", "Station identifier."),
        ("bird_age_days", "farm batch context", "Chicken age in days."),
        ("breed_code", "farm batch context", "Breed or line code."),
        ("camera_position_code", "site deployment config", "Camera position or lane code."),
        ("captured_at", "capture metadata timestamp", "Capture timestamp in UTC."),
    ]
    label_fields = [
        ("final_weight_kg", "edge-weighvision-session.weight_sessions.final_weight_kg", "Operational ground-truth weight used for validation."),
        ("load_cell_weight_kg", "capture metadata scale.weight_kg", "Load-cell weight attached to the selected capture."),
    ]

    return WeighVisionDatasetContractResponse(
        contractName="farmiq.weighvision.weight-prediction-training-dataset",
        version="1.0.0",
        featureSchemaVersion="wv-feature-schema-v1",
        entityKeys=entity_keys,
        featureFields=[
            WeighVisionDatasetField(
                name=name,
                role="feature",
                dataType="number",
                required=True,
                source=source,
                description=description,
            )
            for name, source, description in feature_fields
        ],
        contextFields=[
            WeighVisionDatasetField(
                name=name,
                role="context",
                dataType="datetime" if name == "captured_at" else "string" if name.endswith("_id") or name.endswith("_code") else "integer",
                required=name in {"farm_id", "barn_id", "captured_at"},
                source=source,
                description=description,
            )
            for name, source, description in context_fields
        ],
        labelFields=[
            WeighVisionDatasetField(
                name=name,
                role="label",
                dataType="number",
                required=True,
                source=source,
                description=description,
            )
            for name, source, description in label_fields
        ],
        splitPolicy={
            "training": "time-based split by captured_at",
            "validation": "latest 20 percent of captures per tenant or site",
            "grouping": ["tenant_id", "farm_id", "barn_id"],
            "leakage_guard": "session_id and capture_id must not cross train/validation boundary",
        },
        notes=[
            "Cloud training uses synchronized Edge normalized features, not raw segmentation masks directly.",
            "Prediction remains Edge-executed; Cloud owns contract, registry, subscription, and approval state.",
        ],
    )


def default_activation_policy(feature_schema_version: str) -> dict[str, Any]:
    return {
        "feature_schema_version": feature_schema_version,
        "require_checksum_validation": True,
        "require_feature_schema_match": True,
        "max_activation_failures": 3,
        "activation_mode": "shadow",
    }


def default_fallback_policy() -> dict[str, Any]:
    return {
        "order": ["site_pinned_fallback", "last_known_good", "stub_mode"],
        "preserve_shadow_prediction": True,
        "block_operational_decision_override": True,
    }


def package_response_from_row(row: dict[str, Any]) -> WeighVisionModelPackageResponse:
    manifest = json_object_from_row(row.get("manifest"))
    return WeighVisionModelPackageResponse(
        id=row["id"],
        tenantId=row["tenant_id"],
        modelId=row["model_id"],
        packageVersion=row["package_version"],
        runtimeFamily=row["runtime_family"],
        runtimeVersion=row["runtime_version"],
        featureSchemaVersion=row["feature_schema_version"],
        checksumSha256=row["checksum_sha256"],
        packageUri=row["package_uri"],
        channel=row["channel"],
        approvalState=row["approval_state"],
        manifest=WeighVisionPackageManifest(**manifest),
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def subscription_response_from_row(row: dict[str, Any]) -> WeighVisionSiteSubscriptionResponse:
    return WeighVisionSiteSubscriptionResponse(
        id=row["id"],
        tenantId=row["tenant_id"],
        siteId=row["site_id"],
        farmId=row.get("farm_id"),
        barnId=row.get("barn_id"),
        channel=row["channel"],
        pinnedPackageId=row.get("pinned_package_id"),
        fallbackPackageId=row.get("fallback_package_id"),
        notes=row.get("notes"),
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def model_response_from_row(row: dict[str, Any]) -> ModelResponse:
    hyperparameters = json_list_from_row(row.get("hyperparameters"))
    features = json_list_from_row(row.get("features"))
    metrics = json_list_from_row(row.get("metrics"))
    metadata = json_object_from_row(row.get("metadata"))
    return ModelResponse(
        id=row["id"],
        tenantId=row["tenant_id"],
        name=row["name"],
        type=row["type"],
        description=row["description"],
        algorithm=row["algorithm"],
        hyperparameters=[ModelHyperparameter(**h) for h in hyperparameters],
        features=[str(feature) for feature in features],
        targetVariable=row["target_variable"],
        status=row["status"],
        metrics=[ModelMetric(**m) for m in metrics],
        metadata=ModelMetadata(**metadata),
        trainingDataStart=row["training_data_start"],
        trainingDataEnd=row["training_data_end"],
        trainedAt=row["trained_at"],
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def metric_list_from_mapping(metrics: dict[str, float]) -> list[ModelMetric]:
    result: list[ModelMetric] = []
    for name, value in metrics.items():
        unit = "kg" if name.endswith("_kg") else None
        result.append(ModelMetric(name=name, value=float(value), unit=unit))
    return result


def json_value_from_row(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def json_list_from_row(value: Any) -> list[Any]:
    parsed = json_value_from_row(value)
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise TypeError(f"Expected list-like JSON field, got {type(parsed).__name__}")
    return parsed


def json_object_from_row(value: Any) -> dict[str, Any]:
    parsed = json_value_from_row(value)
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise TypeError(f"Expected object-like JSON field, got {type(parsed).__name__}")
    return parsed


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> MlModelDb | InMemoryMlModelDb:
    return request.app.state.db


async def verify_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify tenant from Bearer token."""
    # In production, validate JWT token and extract tenant_id
    # For now, assume the token contains the tenant_id
    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    return token


# Model Endpoints


@router.post("/models", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    model_data: ModelCreate,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ModelResponse:
    """Create a new ML model."""
    model_id = settings.new_id()
    now = datetime.now(tz=timezone.utc)

    await db.create_model(
        id=model_id,
        tenant_id=tenant_id,
        name=model_data.name,
        type=model_data.type,
        description=model_data.description,
        algorithm=model_data.algorithm,
        hyperparameters=[h.model_dump() for h in model_data.hyperparameters],
        features=model_data.features,
        target_variable=model_data.targetVariable,
        status="draft",
        metrics=[],
        metadata=model_data.metadata.model_dump(),
        training_data_start=None,
        training_data_end=None,
        trained_at=None,
    )

    model = await db.get_model(model_id=model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create model",
        )

    return ModelResponse(
        id=model["id"],
        tenantId=model["tenant_id"],
        name=model["name"],
        type=model["type"],
        description=model["description"],
        algorithm=model["algorithm"],
        hyperparameters=[ModelHyperparameter(**h) for h in model["hyperparameters"]],
        features=model["features"],
        targetVariable=model["target_variable"],
        status=model["status"],
        metrics=[ModelMetric(**m) for m in model["metrics"]],
        metadata=ModelMetadata(**model["metadata"]),
        trainingDataStart=model["training_data_start"],
        trainingDataEnd=model["training_data_end"],
        trainedAt=model["trained_at"],
        createdAt=model["created_at"],
        updatedAt=model["updated_at"],
    )


@router.get("/models/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> ModelResponse:
    """Get a model by ID."""
    model = await db.get_model(model_id=model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    if model["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return ModelResponse(
        id=model["id"],
        tenantId=model["tenant_id"],
        name=model["name"],
        type=model["type"],
        description=model["description"],
        algorithm=model["algorithm"],
        hyperparameters=[ModelHyperparameter(**h) for h in model["hyperparameters"]],
        features=model["features"],
        targetVariable=model["target_variable"],
        status=model["status"],
        metrics=[ModelMetric(**m) for m in model["metrics"]],
        metadata=ModelMetadata(**model["metadata"]),
        trainingDataStart=model["training_data_start"],
        trainingDataEnd=model["training_data_end"],
        trainedAt=model["trained_at"],
        createdAt=model["created_at"],
        updatedAt=model["updated_at"],
    )


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    tenant_id: str = Depends(verify_tenant),
    model_type: ModelType | None = None,
    status: ModelStatus | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> ModelListResponse:
    """List models for a tenant."""
    models, total = await db.list_models(
        tenant_id=tenant_id,
        model_type=model_type,
        status=status,
        page=page,
        limit=limit,
    )

    data = [
        ModelResponse(
            id=m["id"],
            tenantId=m["tenant_id"],
            name=m["name"],
            type=m["type"],
            description=m["description"],
            algorithm=m["algorithm"],
            hyperparameters=[ModelHyperparameter(**h) for h in m["hyperparameters"]],
            features=m["features"],
            targetVariable=m["target_variable"],
            status=m["status"],
            metrics=[ModelMetric(**m) for m in m["metrics"]],
            metadata=ModelMetadata(**m["metadata"]),
            trainingDataStart=m["training_data_start"],
            trainingDataEnd=m["training_data_end"],
            trainedAt=m["trained_at"],
            createdAt=m["created_at"],
            updatedAt=m["updated_at"],
        )
        for m in models
    ]

    return ModelListResponse(
        data=data,
        meta=ListMeta(
            page=page,
            limit=limit,
            total=total,
            hasNext=(page * limit) < total,
        ).model_dump(),
    )


@router.patch("/models/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: str,
    model_data: ModelUpdate,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> ModelResponse:
    """Update a model."""
    existing = await db.get_model(model_id=model_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    if existing["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    model = await db.update_model(
        model_id=model_id,
        name=model_data.name,
        description=model_data.description,
        hyperparameters=[h.model_dump() for h in model_data.hyperparameters] if model_data.hyperparameters else None,
        features=model_data.features,
        tags=model_data.tags,
        status=model_data.status,
    )

    if not model:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update model",
        )

    return ModelResponse(
        id=model["id"],
        tenantId=model["tenant_id"],
        name=model["name"],
        type=model["type"],
        description=model["description"],
        algorithm=model["algorithm"],
        hyperparameters=[ModelHyperparameter(**h) for h in model["hyperparameters"]],
        features=model["features"],
        targetVariable=model["target_variable"],
        status=model["status"],
        metrics=[ModelMetric(**m) for m in model["metrics"]],
        metadata=ModelMetadata(**model["metadata"]),
        trainingDataStart=model["training_data_start"],
        trainingDataEnd=model["training_data_end"],
        trainedAt=model["trained_at"],
        createdAt=model["created_at"],
        updatedAt=model["updated_at"],
    )


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_model(
    model_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> None:
    """Delete a model."""
    existing = await db.get_model(model_id=model_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    if existing["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    success = await db.delete_model(model_id=model_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete model",
        )


# Deployment Endpoints


@router.post("/deployments", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    deployment_data: DeploymentCreate,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DeploymentResponse:
    """Create a new deployment."""
    model = await db.get_model(model_id=deployment_data.modelId)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    if model["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    deployment_id = settings.new_id()

    await db.create_deployment(
        id=deployment_id,
        tenant_id=tenant_id,
        model_id=deployment_data.modelId,
        model_name=model["name"],
        environment=deployment_data.environment,
        config=deployment_data.config.model_dump(),
        status="pending",
        description=deployment_data.description,
    )

    deployment = await db.get_deployment(deployment_id=deployment_id)
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create deployment",
        )

    return DeploymentResponse(
        id=deployment["id"],
        tenantId=deployment["tenant_id"],
        modelId=deployment["model_id"],
        modelName=deployment["model_name"],
        environment=deployment["environment"],
        config=DeploymentConfig(**deployment["config"]),
        status=deployment["status"],
        description=deployment["description"],
        endpointUrl=deployment["endpoint_url"],
        deployedAt=deployment["deployed_at"],
        stoppedAt=deployment["stopped_at"],
        createdAt=deployment["created_at"],
        updatedAt=deployment["updated_at"],
    )


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> DeploymentResponse:
    """Get a deployment by ID."""
    deployment = await db.get_deployment(deployment_id=deployment_id)
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    if deployment["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return DeploymentResponse(
        id=deployment["id"],
        tenantId=deployment["tenant_id"],
        modelId=deployment["model_id"],
        modelName=deployment["model_name"],
        environment=deployment["environment"],
        config=DeploymentConfig(**deployment["config"]),
        status=deployment["status"],
        description=deployment["description"],
        endpointUrl=deployment["endpoint_url"],
        deployedAt=deployment["deployed_at"],
        stoppedAt=deployment["stopped_at"],
        createdAt=deployment["created_at"],
        updatedAt=deployment["updated_at"],
    )


@router.get("/deployments", response_model=DeploymentListResponse)
async def list_deployments(
    tenant_id: str = Depends(verify_tenant),
    model_id: str | None = None,
    environment: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> DeploymentListResponse:
    """List deployments for a tenant."""
    deployments, total = await db.list_deployments(
        tenant_id=tenant_id,
        model_id=model_id,
        environment=environment,
        page=page,
        limit=limit,
    )

    data = [
        DeploymentResponse(
            id=d["id"],
            tenantId=d["tenant_id"],
            modelId=d["model_id"],
            modelName=d["model_name"],
            environment=d["environment"],
            config=DeploymentConfig(**d["config"]),
            status=d["status"],
            description=d["description"],
            endpointUrl=d["endpoint_url"],
            deployedAt=d["deployed_at"],
            stoppedAt=d["stopped_at"],
            createdAt=d["created_at"],
            updatedAt=d["updated_at"],
        )
        for d in deployments
    ]

    return DeploymentListResponse(
        data=data,
        meta=ListMeta(
            page=page,
            limit=limit,
            total=total,
            hasNext=(page * limit) < total,
        ).model_dump(),
    )


@router.patch("/deployments/{deployment_id}", response_model=DeploymentResponse)
async def update_deployment(
    deployment_id: str,
    deployment_data: DeploymentUpdate,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> DeploymentResponse:
    """Update a deployment."""
    existing = await db.get_deployment(deployment_id=deployment_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    if existing["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    deployment = await db.update_deployment(
        deployment_id=deployment_id,
        config=deployment_data.config.model_dump() if deployment_data.config else None,
        description=deployment_data.description,
        status=deployment_data.status,
        endpoint_url=None,
        deployed_at=None,
        stopped_at=None,
    )

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update deployment",
        )

    return DeploymentResponse(
        id=deployment["id"],
        tenantId=deployment["tenant_id"],
        modelId=deployment["model_id"],
        modelName=deployment["model_name"],
        environment=deployment["environment"],
        config=DeploymentConfig(**deployment["config"]),
        status=deployment["status"],
        description=deployment["description"],
        endpointUrl=deployment["endpoint_url"],
        deployedAt=deployment["deployed_at"],
        stoppedAt=deployment["stopped_at"],
        createdAt=deployment["created_at"],
        updatedAt=deployment["updated_at"],
    )


@router.delete("/deployments/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_deployment(
    deployment_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> None:
    """Delete a deployment."""
    existing = await db.get_deployment(deployment_id=deployment_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found",
        )

    if existing["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    success = await db.delete_deployment(deployment_id=deployment_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete deployment",
        )


# Training Endpoints


@router.post("/models/{model_id}/train", response_model=TrainingResponse, status_code=status.HTTP_202_ACCEPTED)
async def train_model(
    model_id: str,
    training_data: TrainingRequest,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TrainingResponse:
    """Start training for a model."""
    model = await db.get_model(model_id=model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    if model["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    training_id = settings.new_id()

    await db.create_training(
        id=training_id,
        model_id=model_id,
        tenant_id=tenant_id,
        training_data_start=training_data.trainingDataStart,
        training_data_end=training_data.trainingDataEnd,
        validation_split=training_data.validationSplit,
        hyperparameters=[h.model_dump() for h in training_data.hyperparameters] if training_data.hyperparameters else [],
        status="queued",
    )

    return TrainingResponse(
        trainingId=training_id,
        modelId=model_id,
        status="queued",
        startedAt=None,
        completedAt=None,
        metrics=[],
        error=None,
    )


@router.get("/trainings/{training_id}", response_model=TrainingResponse)
async def get_training(
    training_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> TrainingResponse:
    """Get training status by ID."""
    training = await db.get_training(training_id=training_id)
    if not training:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training not found",
        )

    if training["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return TrainingResponse(
        trainingId=training["id"],
        modelId=training["model_id"],
        status=training["status"],
        startedAt=training["started_at"],
        completedAt=training["completed_at"],
        metrics=[ModelMetric(**m) for m in training["metrics"]],
        error=training["error"],
    )


async def resolve_site_package(
    *,
    db: MlModelDb | InMemoryMlModelDb,
    tenant_id: str,
    site_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    subscription = await db.get_site_subscription(tenant_id=tenant_id, site_id=site_id)
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    packages, _ = await db.list_model_packages(
        tenant_id=tenant_id,
        channel=None if subscription["channel"] == "pinned" else subscription["channel"],
        approval_state="published",
        page=1,
        limit=100,
    )
    packages_by_id = {pkg["id"]: pkg for pkg in packages}

    active_package: dict[str, Any] | None = None
    if subscription["channel"] == "pinned":
        pinned_id = subscription.get("pinned_package_id")
        if not pinned_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pinned subscription has no pinned package")
        active_package = await db.get_model_package(package_id=pinned_id)
        if not active_package or active_package["tenant_id"] != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pinned package not found")
    else:
        if not packages:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No published package available for channel")
        active_package = packages[0]

    fallback_package = None
    fallback_id = subscription.get("fallback_package_id")
    if fallback_id:
        fallback_package = packages_by_id.get(fallback_id) or await db.get_model_package(package_id=fallback_id)

    return active_package, fallback_package, subscription


@router.get("/weighvision/dataset-contract", response_model=WeighVisionDatasetContractResponse)
async def get_weighvision_dataset_contract(
    _tenant_id: str = Depends(verify_tenant),
) -> WeighVisionDatasetContractResponse:
    return dataset_contract_payload()


@router.post(
    "/weighvision/bootstrap-baseline",
    response_model=WeighVisionBaselineBootstrapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_weighvision_baseline(
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WeighVisionBaselineBootstrapResponse:
    contract = dataset_contract_payload()

    existing_models, _ = await db.list_models(
        tenant_id=tenant_id,
        model_type="regression",
        status=None,
        page=1,
        limit=100,
    )
    baseline_model = next((m for m in existing_models if m["name"] == "weighvision-weight-shadow-baseline"), None)
    if not baseline_model:
        model_id = settings.new_id()
        await db.create_model(
            id=model_id,
            tenant_id=tenant_id,
            name="weighvision-weight-shadow-baseline",
            type="regression",
            description="Cloud baseline regression model for Edge shadow chicken-weight prediction.",
            algorithm="xgboost-regressor-baseline",
            hyperparameters=[
                {"name": "max_depth", "value": 6, "type": "number"},
                {"name": "learning_rate", "value": 0.1, "type": "number"},
            ],
            features=[field.name for field in contract.featureFields] + [field.name for field in contract.contextFields],
            target_variable="final_weight_kg",
            status="trained",
            metrics=[
                {"name": "mae_kg", "value": 0.18, "unit": "kg"},
                {"name": "rmse_kg", "value": 0.24, "unit": "kg"},
            ],
            metadata={
                "author": "FarmIQ Batch4 bootstrap",
                "description": "Bootstrap baseline for subscription-control-plane bring-up",
                "tags": ["weighvision", "shadow", "baseline"],
                "version": "1.0.0",
            },
            training_data_start=None,
            training_data_end=None,
            trained_at=datetime.now(tz=timezone.utc),
        )
        baseline_model = await db.get_model(model_id=model_id)

    assert baseline_model is not None

    packages, _ = await db.list_model_packages(
        tenant_id=tenant_id,
        model_id=baseline_model["id"],
        channel="stable",
        approval_state="published",
        page=1,
        limit=10,
    )
    baseline_package = next((pkg for pkg in packages if pkg["package_version"] == "wv-shadow-baseline-1.0.0"), None)
    if not baseline_package:
        package_id = settings.new_id()
        manifest = WeighVisionPackageManifest(
            packageVersion="wv-shadow-baseline-1.0.0",
            modelFamily="weighvision-weight-predictor",
            runtimeFamily="python-fastapi",
            runtimeVersion="1.0.0",
            featureSchemaVersion=contract.featureSchemaVersion,
            checksumSha256="bootstrap-shadow-baseline-checksum",
            packageUri="s3://farmiq-models/weighvision/wv-shadow-baseline-1.0.0.tar.gz",
            entrypoint="model.pkl",
            channel="stable",
            activationPolicy=default_activation_policy(contract.featureSchemaVersion),
            fallbackPolicy=default_fallback_policy(),
            metadata={
                "model_version": "1.0.0",
                "training_cutoff": "bootstrap",
                "shadow_mode_only": True,
            },
        )
        await db.create_model_package(
            id=package_id,
            tenant_id=tenant_id,
            model_id=baseline_model["id"],
            package_version=manifest.packageVersion,
            runtime_family=manifest.runtimeFamily,
            runtime_version=manifest.runtimeVersion,
            feature_schema_version=manifest.featureSchemaVersion,
            checksum_sha256=manifest.checksumSha256,
            package_uri=manifest.packageUri,
            channel=manifest.channel,
            approval_state="published",
            manifest=manifest.model_dump(),
        )
        baseline_package = await db.get_model_package(package_id=package_id)

    assert baseline_package is not None

    return WeighVisionBaselineBootstrapResponse(
        datasetContract=contract,
        model=model_response_from_row(baseline_model),
        package=package_response_from_row(baseline_package),
    )


@router.post(
    "/weighvision/train-baseline",
    response_model=WeighVisionBaselineTrainingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def train_weighvision_baseline(
    training_request: WeighVisionBaselineTrainingRequest,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WeighVisionBaselineTrainingResponse:
    contract = dataset_contract_payload()
    dataset_path = Path(training_request.datasetPath or settings.default_weighvision_dataset_path).expanduser().resolve()
    if not dataset_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset not found: {dataset_path}")

    timestamp_suffix = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
    package_version = training_request.packageVersion or f"wv-shadow-baseline-{timestamp_suffix}"
    artifact_root = Path(settings.artifact_root_dir).expanduser().resolve() / tenant_id
    artifact_root.mkdir(parents=True, exist_ok=True)

    artifacts = train_and_package_baseline(
        dataset_path=dataset_path,
        package_version=package_version,
        output_root=artifact_root,
        contract=contract,
    )

    model_id = settings.new_id()
    validation_metrics = metric_list_from_mapping(artifacts.validation_metrics)
    await db.create_model(
        id=model_id,
        tenant_id=tenant_id,
        name=f"weighvision-weight-shadow-baseline-{package_version}",
        type="regression",
        description="Trained linear-regression baseline for Edge-executed shadow chicken-weight prediction.",
        algorithm="linear-regression",
        hyperparameters=[
            {"name": "feature_scaling", "value": "zscore", "type": "string"},
            {"name": "ridge_lambda", "value": 1e-6, "type": "number"},
        ],
        features=artifacts.feature_names,
        target_variable="final_weight_kg",
        status="trained",
        metrics=[metric.model_dump() for metric in validation_metrics],
        metadata={
            "author": "FarmIQ Batch4 trainer",
            "description": f"Baseline training artifact from {dataset_path.name}",
            "tags": ["weighvision", "shadow", "baseline", "trained"],
            "version": package_version,
        },
        training_data_start=artifacts.generated_at,
        training_data_end=artifacts.generated_at,
        trained_at=artifacts.generated_at,
    )
    model_row = await db.get_model(model_id=model_id)
    assert model_row is not None

    package_id = settings.new_id()
    package_uri = (
        f"{settings.artifact_base_url.rstrip('/')}/api/v1/ml/weighvision/model-packages/{package_id}/download"
    )
    manifest = WeighVisionPackageManifest(
        packageVersion=package_version,
        modelFamily="weighvision-weight-predictor",
        runtimeFamily="python-linear-regression",
        runtimeVersion="1.0.0",
        featureSchemaVersion=contract.featureSchemaVersion,
        checksumSha256=artifacts.checksum_sha256,
        packageUri=package_uri,
        entrypoint="model/model.json",
        channel=training_request.channel,
        activationPolicy=default_activation_policy(contract.featureSchemaVersion),
        fallbackPolicy=default_fallback_policy(),
        metadata={
            "model_version": package_version,
            "local_artifact_path": str(artifacts.package_file),
            "dataset_path": str(dataset_path),
            "dataset_rows": artifacts.dataset_rows,
            "training_rows": artifacts.training_rows,
            "validation_rows": artifacts.validation_rows,
            "train_metrics": artifacts.train_metrics,
            "validation_metrics": artifacts.validation_metrics,
            "naive_metrics": artifacts.naive_metrics,
            "shadow_mode_only": True,
        },
    )
    await db.create_model_package(
        id=package_id,
        tenant_id=tenant_id,
        model_id=model_id,
        package_version=package_version,
        runtime_family=manifest.runtimeFamily,
        runtime_version=manifest.runtimeVersion,
        feature_schema_version=manifest.featureSchemaVersion,
        checksum_sha256=artifacts.checksum_sha256,
        package_uri=package_uri,
        channel=manifest.channel,
        approval_state=training_request.approvalState,
        manifest=manifest.model_dump(),
    )
    package_row = await db.get_model_package(package_id=package_id)
    assert package_row is not None

    return WeighVisionBaselineTrainingResponse(
        datasetContract=contract,
        model=model_response_from_row(model_row),
        package=package_response_from_row(package_row),
        datasetPath=str(dataset_path),
        datasetRows=artifacts.dataset_rows,
        trainingRows=artifacts.training_rows,
        validationRows=artifacts.validation_rows,
        featureNames=artifacts.feature_names,
        trainMetrics=metric_list_from_mapping(artifacts.train_metrics),
        validationMetrics=validation_metrics,
        naiveMetrics=metric_list_from_mapping(artifacts.naive_metrics),
    )


@router.post("/weighvision/model-packages", response_model=WeighVisionModelPackageResponse, status_code=status.HTTP_201_CREATED)
async def create_weighvision_model_package(
    package_data: WeighVisionModelPackageCreate,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WeighVisionModelPackageResponse:
    model = await db.get_model(model_id=package_data.modelId)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    if model["tenant_id"] != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    package_id = settings.new_id()
    await db.create_model_package(
        id=package_id,
        tenant_id=tenant_id,
        model_id=package_data.modelId,
        package_version=package_data.packageVersion,
        runtime_family=package_data.runtimeFamily,
        runtime_version=package_data.runtimeVersion,
        feature_schema_version=package_data.featureSchemaVersion,
        checksum_sha256=package_data.checksumSha256,
        package_uri=package_data.packageUri,
        channel=package_data.channel,
        approval_state=package_data.approvalState,
        manifest=package_data.manifest.model_dump(),
    )
    package_row = await db.get_model_package(package_id=package_id)
    assert package_row is not None
    return package_response_from_row(package_row)


@router.get("/weighvision/model-packages", response_model=WeighVisionModelPackageListResponse)
async def list_weighvision_model_packages(
    tenant_id: str = Depends(verify_tenant),
    model_id: str | None = None,
    channel: str | None = None,
    approval_state: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> WeighVisionModelPackageListResponse:
    packages, total = await db.list_model_packages(
        tenant_id=tenant_id,
        model_id=model_id,
        channel=channel,
        approval_state=approval_state,
        page=page,
        limit=limit,
    )
    return WeighVisionModelPackageListResponse(
        data=[package_response_from_row(pkg) for pkg in packages],
        meta=ListMeta(page=page, limit=limit, total=total, hasNext=(page * limit) < total).model_dump(),
    )


@router.get("/weighvision/model-packages/{package_id}", response_model=WeighVisionModelPackageResponse)
async def get_weighvision_model_package(
    package_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> WeighVisionModelPackageResponse:
    package_row = await db.get_model_package(package_id=package_id)
    if not package_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model package not found")
    if package_row["tenant_id"] != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return package_response_from_row(package_row)


@router.get("/weighvision/model-packages/{package_id}/download")
async def download_weighvision_model_package(
    package_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
):
    package_row = await db.get_model_package(package_id=package_id)
    if not package_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model package not found")
    if package_row["tenant_id"] != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    manifest = json_object_from_row(package_row.get("manifest"))
    local_artifact_path = manifest.get("metadata", {}).get("local_artifact_path")
    if not local_artifact_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package artifact path not available")

    artifact_path = Path(str(local_artifact_path)).expanduser().resolve()
    if not artifact_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package artifact not found on disk")

    return FileResponse(
        path=str(artifact_path),
        media_type="application/gzip",
        filename=artifact_path.name,
    )


@router.put("/weighvision/model-subscriptions/sites/{site_id}", response_model=WeighVisionSiteSubscriptionResponse)
async def upsert_weighvision_site_subscription(
    site_id: str,
    subscription_data: WeighVisionSiteSubscriptionUpsert,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WeighVisionSiteSubscriptionResponse:
    if subscription_data.tenantId != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenantId does not match bearer tenant")
    if subscription_data.siteId != site_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="siteId in path/body mismatch")

    if subscription_data.pinnedPackageId:
        package_row = await db.get_model_package(package_id=subscription_data.pinnedPackageId)
        if not package_row or package_row["tenant_id"] != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pinned package not found")

    if subscription_data.fallbackPackageId:
        fallback_row = await db.get_model_package(package_id=subscription_data.fallbackPackageId)
        if not fallback_row or fallback_row["tenant_id"] != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fallback package not found")

    row = await db.upsert_site_subscription(
        id=settings.new_id(),
        tenant_id=tenant_id,
        site_id=site_id,
        farm_id=subscription_data.farmId,
        barn_id=subscription_data.barnId,
        channel=subscription_data.channel,
        pinned_package_id=subscription_data.pinnedPackageId,
        fallback_package_id=subscription_data.fallbackPackageId,
        notes=subscription_data.notes,
    )
    return subscription_response_from_row(row)


@router.get("/weighvision/model-subscriptions/sites/{site_id}", response_model=WeighVisionSiteSubscriptionResponse)
async def get_weighvision_site_subscription(
    site_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> WeighVisionSiteSubscriptionResponse:
    row = await db.get_site_subscription(tenant_id=tenant_id, site_id=site_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return subscription_response_from_row(row)


@router.get("/weighvision/model-subscriptions/sites/{site_id}/resolve", response_model=WeighVisionSiteSubscriptionResolveResponse)
async def resolve_weighvision_site_subscription(
    site_id: str,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
) -> WeighVisionSiteSubscriptionResolveResponse:
    active_package, fallback_package, subscription = await resolve_site_package(
        db=db,
        tenant_id=tenant_id,
        site_id=site_id,
    )
    active_manifest = json_object_from_row(active_package.get("manifest"))
    return WeighVisionSiteSubscriptionResolveResponse(
        tenantId=tenant_id,
        siteId=site_id,
        farmId=subscription.get("farm_id"),
        barnId=subscription.get("barn_id"),
        channel=subscription["channel"],
        activePackage=package_response_from_row(active_package),
        fallbackPackage=package_response_from_row(fallback_package) if fallback_package else None,
        activationPolicy=active_manifest.get(
            "activationPolicy",
            default_activation_policy(active_package["feature_schema_version"]),
        ),
        fallbackPolicy=active_manifest.get("fallbackPolicy", default_fallback_policy()),
    )


@router.post("/weighvision/model-subscriptions/sites/{site_id}/ack", response_model=WeighVisionSiteSubscriptionAckResponse, status_code=status.HTTP_201_CREATED)
async def ack_weighvision_site_subscription(
    site_id: str,
    ack_data: WeighVisionSiteSubscriptionAckRequest,
    tenant_id: str = Depends(verify_tenant),
    db: MlModelDb | InMemoryMlModelDb = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WeighVisionSiteSubscriptionAckResponse:
    if ack_data.tenantId != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenantId does not match bearer tenant")

    subscription = await db.get_site_subscription(tenant_id=tenant_id, site_id=site_id)
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    package_row = await db.get_model_package(package_id=ack_data.packageId)
    if not package_row or package_row["tenant_id"] != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")

    ack_row = await db.create_site_subscription_ack(
        id=settings.new_id(),
        tenant_id=tenant_id,
        site_id=site_id,
        package_id=ack_data.packageId,
        ack_type=ack_data.ackType,
        status=ack_data.status,
        detail=ack_data.detail,
        payload=ack_data.payload,
    )
    return WeighVisionSiteSubscriptionAckResponse(
        id=ack_row["id"],
        tenantId=ack_row["tenant_id"],
        siteId=ack_row["site_id"],
        packageId=ack_row["package_id"],
        ackType=ack_row["ack_type"],
        status=ack_row["status"],
        detail=ack_row.get("detail"),
        payload=ack_row.get("payload") or {},
        createdAt=ack_row["created_at"],
    )
