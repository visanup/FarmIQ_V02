from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# Model Type Literals
ModelType = Literal[
    "forecast",
    "anomaly_detection",
    "classification",
    "regression",
    "clustering",
    "recommendation"
]

# Model Status Literals
ModelStatus = Literal["draft", "training", "trained", "deployed", "deprecated"]

# Deployment Status Literals
DeploymentStatus = Literal["pending", "active", "stopped", "failed"]


class ModelHyperparameter(BaseModel):
    name: str
    value: Any
    type: Literal["string", "number", "boolean", "array"]


class ModelMetric(BaseModel):
    name: str
    value: float
    unit: Optional[str] = None
    threshold: Optional[float] = None


class ModelMetadata(BaseModel):
    author: str
    description: str
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"


class ModelCreate(BaseModel):
    tenantId: str
    name: str
    type: ModelType
    description: str
    algorithm: str
    hyperparameters: list[ModelHyperparameter] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    targetVariable: str
    metadata: ModelMetadata


class ModelUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    hyperparameters: Optional[list[ModelHyperparameter]] = None
    features: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    status: Optional[ModelStatus] = None


class ModelResponse(BaseModel):
    id: str
    tenantId: str
    name: str
    type: ModelType
    description: str
    algorithm: str
    hyperparameters: list[ModelHyperparameter] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    targetVariable: str
    status: ModelStatus
    metrics: list[ModelMetric] = Field(default_factory=list)
    metadata: ModelMetadata
    trainingDataStart: Optional[datetime] = None
    trainingDataEnd: Optional[datetime] = None
    trainedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime


class ModelListResponse(BaseModel):
    data: list[ModelResponse]
    meta: dict[str, Any]


# Deployment Schemas


class DeploymentConfig(BaseModel):
    instanceCount: int = 1
    cpuLimit: str = "1000m"
    memoryLimit: str = "1Gi"
    autoScaleEnabled: bool = False
    autoScaleMinInstances: int = 1
    autoScaleMaxInstances: int = 3


class DeploymentCreate(BaseModel):
    tenantId: str
    modelId: str
    environment: Literal["dev", "staging", "production"]
    config: DeploymentConfig = Field(default_factory=DeploymentConfig)
    description: Optional[str] = None


class DeploymentUpdate(BaseModel):
    config: Optional[DeploymentConfig] = None
    description: Optional[str] = None
    status: Optional[DeploymentStatus] = None


class DeploymentResponse(BaseModel):
    id: str
    tenantId: str
    modelId: str
    modelName: str
    environment: Literal["dev", "staging", "production"]
    config: DeploymentConfig
    status: DeploymentStatus
    description: Optional[str] = None
    endpointUrl: Optional[str] = None
    deployedAt: Optional[datetime] = None
    stoppedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime


class DeploymentListResponse(BaseModel):
    data: list[DeploymentResponse]
    meta: dict[str, Any]


# Training Request Schemas


class TrainingRequest(BaseModel):
    modelId: str
    tenantId: str
    trainingDataStart: datetime
    trainingDataEnd: datetime
    validationSplit: float = 0.2
    hyperparameters: Optional[list[ModelHyperparameter]] = None


class TrainingResponse(BaseModel):
    trainingId: str
    modelId: str
    status: Literal["queued", "running", "completed", "failed"]
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    metrics: list[ModelMetric] = Field(default_factory=list)
    error: Optional[str] = None


# Prediction Request/Response Schemas


class PredictionRequest(BaseModel):
    modelId: str
    tenantId: str
    features: dict[str, Any]
    requestId: Optional[str] = None


class PredictionResponse(BaseModel):
    requestId: str
    modelId: str
    prediction: Any
    confidence: Optional[float] = None
    timestamp: datetime


# List Meta


class ListMeta(BaseModel):
    page: int
    limit: int
    total: int
    hasNext: bool


# WeighVision Cloud-Edge control plane schemas

ApprovalState = Literal["draft", "approved", "published", "deprecated"]
SubscriptionChannel = Literal["stable", "candidate", "pinned"]
SubscriptionAckType = Literal["downloaded", "validated", "activated", "rollback", "failed"]


class WeighVisionDatasetField(BaseModel):
    name: str
    role: Literal["entity", "feature", "context", "label"]
    dataType: Literal["string", "integer", "number", "boolean", "datetime", "json"]
    required: bool
    source: str
    description: str


class WeighVisionDatasetContractResponse(BaseModel):
    contractName: str
    version: str
    featureSchemaVersion: str
    entityKeys: list[WeighVisionDatasetField]
    featureFields: list[WeighVisionDatasetField]
    contextFields: list[WeighVisionDatasetField]
    labelFields: list[WeighVisionDatasetField]
    splitPolicy: dict[str, Any]
    notes: list[str] = Field(default_factory=list)


class WeighVisionPackageManifest(BaseModel):
    packageVersion: str
    modelFamily: str
    runtimeFamily: str
    runtimeVersion: str
    featureSchemaVersion: str
    checksumSha256: str
    packageUri: str
    entrypoint: str
    channel: SubscriptionChannel
    activationPolicy: dict[str, Any]
    fallbackPolicy: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class WeighVisionModelPackageCreate(BaseModel):
    modelId: str
    packageVersion: str
    runtimeFamily: str
    runtimeVersion: str
    featureSchemaVersion: str
    checksumSha256: str
    packageUri: str
    channel: SubscriptionChannel
    approvalState: ApprovalState = "draft"
    manifest: WeighVisionPackageManifest


class WeighVisionModelPackageResponse(BaseModel):
    id: str
    tenantId: str
    modelId: str
    packageVersion: str
    runtimeFamily: str
    runtimeVersion: str
    featureSchemaVersion: str
    checksumSha256: str
    packageUri: str
    channel: SubscriptionChannel
    approvalState: ApprovalState
    manifest: WeighVisionPackageManifest
    createdAt: datetime
    updatedAt: datetime


class WeighVisionModelPackageListResponse(BaseModel):
    data: list[WeighVisionModelPackageResponse]
    meta: dict[str, Any]


class WeighVisionBaselineBootstrapResponse(BaseModel):
    datasetContract: WeighVisionDatasetContractResponse
    model: ModelResponse
    package: WeighVisionModelPackageResponse


class WeighVisionBaselineTrainingRequest(BaseModel):
    datasetPath: Optional[str] = None
    packageVersion: Optional[str] = None
    channel: SubscriptionChannel = "stable"
    approvalState: ApprovalState = "published"


class WeighVisionBaselineTrainingResponse(BaseModel):
    datasetContract: WeighVisionDatasetContractResponse
    model: ModelResponse
    package: WeighVisionModelPackageResponse
    datasetPath: str
    datasetRows: int
    trainingRows: int
    validationRows: int
    featureNames: list[str]
    trainMetrics: list[ModelMetric] = Field(default_factory=list)
    validationMetrics: list[ModelMetric] = Field(default_factory=list)
    naiveMetrics: list[ModelMetric] = Field(default_factory=list)


class WeighVisionSiteSubscriptionUpsert(BaseModel):
    tenantId: str
    siteId: str
    farmId: Optional[str] = None
    barnId: Optional[str] = None
    channel: SubscriptionChannel = "stable"
    pinnedPackageId: Optional[str] = None
    fallbackPackageId: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("pinnedPackageId")
    @classmethod
    def validate_pinned_for_channel(cls, value: Optional[str], info):  # type: ignore[override]
        channel = info.data.get("channel")
        if channel == "pinned" and not value:
            raise ValueError("pinnedPackageId is required when channel is pinned")
        return value


class WeighVisionSiteSubscriptionResponse(BaseModel):
    id: str
    tenantId: str
    siteId: str
    farmId: Optional[str] = None
    barnId: Optional[str] = None
    channel: SubscriptionChannel
    pinnedPackageId: Optional[str] = None
    fallbackPackageId: Optional[str] = None
    notes: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime


class WeighVisionSiteSubscriptionResolveResponse(BaseModel):
    tenantId: str
    siteId: str
    farmId: Optional[str] = None
    barnId: Optional[str] = None
    channel: SubscriptionChannel
    activePackage: WeighVisionModelPackageResponse
    fallbackPackage: Optional[WeighVisionModelPackageResponse] = None
    activationPolicy: dict[str, Any]
    fallbackPolicy: dict[str, Any]


class WeighVisionSiteSubscriptionAckRequest(BaseModel):
    tenantId: str
    packageId: str
    ackType: SubscriptionAckType
    status: Literal["ok", "failed"]
    detail: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WeighVisionSiteSubscriptionAckResponse(BaseModel):
    id: str
    tenantId: str
    siteId: str
    packageId: str
    ackType: SubscriptionAckType
    status: Literal["ok", "failed"]
    detail: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime
