"""API endpoints for inference service."""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, AliasChoices
import logging

from app.db import InferenceDb
from app.job_service import JobService
from app.inference_service import InferenceService
from app.config import Config

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models
class PerChickenRecord(BaseModel):
    """One stable, independently inferable animal record from a capture."""

    record_id: str
    session_id: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("session_id", "sessionId")
    )
    chicken_index: Optional[int] = Field(
        default=None, validation_alias=AliasChoices("chicken_index", "chickenIndex")
    )
    chicken_count: Optional[int] = Field(
        default=None, validation_alias=AliasChoices("chicken_count", "chickenCount")
    )
    bbox_xyxy: List[float] = Field(
        validation_alias=AliasChoices("bbox_xyxy", "bboxXyxy"), min_length=4, max_length=4
    )
    confidence_score: Optional[float] = Field(
        default=None, validation_alias=AliasChoices("confidence_score", "confidenceScore")
    )
    mask_path: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("mask_path", "maskPath")
    )
    weight_label_type: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("weight_label_type", "weightLabelType")
    )


class CreateJobRequest(BaseModel):
    # Accept both snake_case and camelCase for internal callers.
    tenant_id: str = Field(validation_alias=AliasChoices("tenant_id", "tenantId"))
    farm_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("farm_id", "farmId"))
    barn_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("barn_id", "barnId"))
    device_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("device_id", "deviceId"))
    station_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("station_id", "stationId"))
    session_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("session_id", "sessionId"))
    media_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("media_id", "mediaId"))
    object_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("object_key", "objectKey"))
    trace_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("trace_id", "traceId"))
    job_type: Optional[str] = Field(default="inference", validation_alias=AliasChoices("job_type", "jobType"))
    per_chicken_records: Optional[List[PerChickenRecord]] = Field(
        default=None, validation_alias=AliasChoices("per_chicken_records", "perChickenRecords")
    )
    session_aggregate: Optional[Dict[str, Any]] = Field(
        default=None, validation_alias=AliasChoices("session_aggregate", "sessionAggregate")
    )
    filtering_summary: Optional[Dict[str, Any]] = Field(
        default=None, validation_alias=AliasChoices("filtering_summary", "filteringSummary")
    )


class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    updated_at: str


class InferenceResult(BaseModel):
    id: str
    tenant_id: str
    session_id: Optional[str]
    media_id: Optional[str]
    predicted_weight_kg: Optional[float]
    confidence: Optional[float]
    model_version: str
    occurred_at: str


@router.post("/jobs", response_model=JobResponse, tags=["Inference"])
async def create_job(request: Request, job_request: CreateJobRequest):
    """Create a new inference job."""
    try:
        db: InferenceDb = request.app.state.db
        job_service: JobService = request.app.state.job_service
        
        # Validate required fields
        if not job_request.tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        if not job_request.media_id and not job_request.object_key:
            raise HTTPException(status_code=400, detail="media_id or object_key is required")
        records = job_request.per_chicken_records or []
        if records:
            if not job_request.session_id:
                raise HTTPException(status_code=400, detail="session_id is required with perChickenRecords")
            record_ids = [record.record_id for record in records]
            if len(record_ids) != len(set(record_ids)):
                raise HTTPException(status_code=400, detail="perChickenRecords record_id values must be unique")
            if any(record.session_id and record.session_id != job_request.session_id for record in records):
                raise HTTPException(status_code=400, detail="perChickenRecords session_id must match session_id")

        tenant_header = request.headers.get("x-tenant-id")
        if tenant_header and tenant_header != job_request.tenant_id:
            raise HTTPException(status_code=403, detail="x-tenant-id does not match tenant_id")
        
        # Get trace_id from request headers or use provided
        trace_id = job_request.trace_id or request.headers.get("x-trace-id") or Config.new_id()
        
        # Create job
        job = await job_service.create_job(
            tenant_id=job_request.tenant_id,
            farm_id=job_request.farm_id or "",
            barn_id=job_request.barn_id or "",
            device_id=job_request.device_id or "",
            station_id=job_request.station_id or "",
            media_id=job_request.media_id,
            object_key=job_request.object_key,
            session_id=job_request.session_id,
            trace_id=trace_id,
            per_chicken_records=[record.model_dump(by_alias=False) for record in records],
            session_aggregate=job_request.session_aggregate,
            filtering_summary=job_request.filtering_summary,
        )
        
        return JobResponse(
            job_id=job["job_id"],
            status=job["status"],
            created_at=job["created_at"],
            updated_at=job["updated_at"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create job", extra={"error": str(e)}, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", tags=["Inference"])
async def get_job(request: Request, job_id: str):
    """Get job status by ID."""
    try:
        job_service: JobService = request.app.state.job_service
        job = await job_service.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results", tags=["Inference"])
async def get_results(
    request: Request,
    sessionId: str = Query(..., description="Session ID"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results")
):
    """Get inference results by session ID."""
    try:
        job_service: JobService = request.app.state.job_service
        results = await job_service.get_results_by_session(sessionId, limit)
        
        return {
            "session_id": sessionId,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Failed to get results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", tags=["Inference"])
async def get_stats(request: Request):
    """Get inference statistics."""
    try:
        job_service: JobService = request.app.state.job_service
        db: InferenceDb = request.app.state.db
        
        tenant_header = request.headers.get("x-tenant-id")
        
        # Get total results count
        total_count = await db.get_inference_results_count(tenant_header)
        
        # Get last result timestamp
        last_result = await db.get_last_inference_result_timestamp(tenant_header)
        
        return {
            "total_results": total_count,
            "last_result_at": last_result,
            "tenant_id": tenant_header
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models", tags=["Inference"])
async def get_models(request: Request):
    """Get available models information."""
    try:
        inference_service: InferenceService = request.app.state.inference_service
        model_info = inference_service.get_model_info()
        return model_info
    except Exception as e:
        logger.error(f"Failed to get models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/refresh", tags=["Inference"])
async def refresh_models(request: Request):
    """Refresh subscribed model package from local policy-sync cache."""
    try:
        inference_service: InferenceService = request.app.state.inference_service
        await inference_service.ensure_subscription_activation()
        return inference_service.get_model_info()
    except Exception as e:
        logger.error(f"Failed to refresh models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
