import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class CreateInferenceJobRequest:
    tenant_id: str
    farm_id: str
    barn_id: str
    device_id: str
    station_id: str
    session_id: str
    media_id: str
    trace_id: Optional[str] = None

    def to_dict(self) -> dict:
        data = {
            "tenantId": self.tenant_id,
            "farmId": self.farm_id,
            "barnId": self.barn_id,
            "deviceId": self.device_id,
            "stationId": self.station_id,
            "sessionId": self.session_id,
            "mediaId": self.media_id,
        }
        if self.trace_id:
            data["traceId"] = self.trace_id
        return data


class InferenceClient:
    def __init__(self, base_url: str, timeout_seconds: int = 15, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def create_job(self, req: CreateInferenceJobRequest, trace_id: Optional[str]) -> bool:
        url = f"{self.base_url}/api/v1/inference/jobs"
        headers = {}
        if trace_id:
            headers["x-trace-id"] = trace_id
            headers["x-request-id"] = trace_id
        headers["x-tenant-id"] = req.tenant_id

        retry_delay = 1.0
        for attempt in range(self.max_retries):
            try:
                resp = self.session.post(
                    url,
                    json=req.to_dict(),
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                if resp.status_code in (200, 201):
                    return True
                logger.warning("Inference API failed %s: %s", resp.status_code, resp.text)
            except requests.RequestException as exc:
                logger.warning("Inference API error: %s", exc)

            if attempt < self.max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
        return False
