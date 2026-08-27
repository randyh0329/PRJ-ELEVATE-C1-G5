import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseModel):
    project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT", "prj-elevate-c1-g5")
    region: str = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
    location: str = os.getenv("VERTEX_AI_LOCATION", "us-central1")
    use_vertex_ai: bool = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true"
    
    # Server ports
    gateway_port: int = int(os.getenv("GATEWAY_PORT", "8000"))
    gateway_host: str = os.getenv("GATEWAY_HOST", "0.0.0.0")
    mock_backend_port: int = int(os.getenv("MOCK_BACKEND_PORT", "8080"))
    
    # Mock URLs
    workweek_mock_url: str = os.getenv("WORKWEEK_MOCK_URL", "http://localhost:8080/api/v1")
    itsm_mock_url: str = os.getenv("ITSM_MOCK_URL", "http://localhost:8080/api/v1")
    
    # Security
    test_auth_secret: str = os.getenv("TEST_AUTH_SECRET", "elevate-test-secret-key-2026")
    dlp_template_digest: str = os.getenv("DLP_TEMPLATE_DIGEST", "sha256:7e41c984fd43d043b3558c4bb10b64177b941584b42fb928e46e890c01a93c9d")
    
    # Environment mode
    environment: str = os.getenv("ENVIRONMENT", "development")
    mock_build: bool = os.getenv("MOCK_BUILD", "true").lower() == "true"
    fidelity_profile: str = os.getenv("FIDELITY_PROFILE", "integration-test")
    
    # Paths
    base_dir: Path = BASE_DIR
    fixtures_dir: Path = BASE_DIR / "fixtures"
    policies_dir: Path = BASE_DIR / "fixtures" / "policies"
    prompts_dir: Path = BASE_DIR / "prompts"
    config_dir: Path = BASE_DIR / "config"
    mocks_dir: Path = BASE_DIR / "mocks"

settings = Settings()
