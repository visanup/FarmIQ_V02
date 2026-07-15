"""Configuration for edge-vision-inference service."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if exists
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

class Config:
    """Application configuration."""
    
    # Server
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://farmiq:farmiq_dev@postgres:5432/farmiq"
    )
    
    # Media store (S3 via edge-media-store)
    MEDIA_STORE_URL: str = os.getenv(
        "MEDIA_STORE_URL",
        "http://edge-media-store:3000"
    )
    
    # Model Configuration
    MODEL_PATH: str = os.getenv("MODEL_PATH", "")
    MODEL_VERSION: str = os.getenv("MODEL_VERSION", "v1.0.0")
    MODEL_MANIFEST_PATH: str = os.getenv("MODEL_MANIFEST_PATH", "")
    FALLBACK_MODEL_MANIFEST_PATH: str = os.getenv("FALLBACK_MODEL_MANIFEST_PATH", "")
    MODEL_CACHE_DIR: str = os.getenv(
        "MODEL_CACHE_DIR",
        str(Path(__file__).parent.parent / "runtime-model-cache"),
    )
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
    NMS_THRESHOLD: float = float(os.getenv("NMS_THRESHOLD", "0.4"))
    MODEL_SYNC_ENABLED: bool = os.getenv("MODEL_SYNC_ENABLED", "true").lower() == "true"

    # Local policy-sync and Cloud control-plane access
    POLICY_SYNC_URL: str = os.getenv(
        "POLICY_SYNC_URL",
        "http://edge-policy-sync:3000/api/v1/edge-config",
    )
    EDGE_TENANT_ID: str = os.getenv("EDGE_TENANT_ID", "")
    EDGE_SITE_ID: str = os.getenv("EDGE_SITE_ID", "")
    MODEL_CONTROL_BFF_URL: str = os.getenv("MODEL_CONTROL_BFF_URL", "")
    MODEL_CONTROL_TOKEN: str = os.getenv("MODEL_CONTROL_TOKEN", "")
    MODEL_CONTROL_TIMEOUT_SECONDS: int = int(os.getenv("MODEL_CONTROL_TIMEOUT_SECONDS", "15"))
    
    # Service URLs
    WEIGHVISION_SESSION_URL: str = os.getenv(
        "WEIGHVISION_SESSION_URL",
        "http://edge-weighvision-session:3000"
    )
    
    # Datadog
    DD_SERVICE: str = os.getenv("DD_SERVICE", "edge-vision-inference")
    DD_ENV: str = os.getenv("DD_ENV", "development")
    
    @staticmethod
    def new_id() -> str:
        """Generate a new UUID v7-like ID (simplified for MVP)."""
        import uuid
        return str(uuid.uuid4())
