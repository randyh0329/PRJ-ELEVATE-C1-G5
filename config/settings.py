"""Application settings and environment configuration."""
from functools import lru_cache
from typing import Optional
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseModel as BaseSettings
    SettingsConfigDict = dict



class Settings(BaseSettings):
    """Centralized configuration for the HR Agentic Solution."""
    
    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    
    # Security & Request Origin
    AUTOMATION_ORIGIN_HEADER: str = "HR_AGENT_ORCHESTRATOR_V1"
    DEFAULT_CALLER_ID: str = "EMP-1001"
    
    # Guardrails
    DEDUPLICATION_WINDOW_MINUTES: int = 30
    MAX_LEAVE_RETRIES: int = 3
    TOOL_TIMEOUT_SECONDS: float = 4.0
    SAFETY_LATENCY_BUDGET_MS: int = 120
    
    # SaaS FastMCP Settings (WorkWeek & ServiceImmediately)
    SAAS_MCP_BASE_URL: str = "https://mock-saas.aishprabhat.demo.altostrat.com"
    SAAS_MCP_CREDENTIAL: str = "mcp_HiIwlFkRL-DrjYgdQvO-fMHg8Q8A_YskI5J00qrP8SA"
    USE_LIVE_MCP: bool = True

    # Future Boilerplate Settings (Live SaaS / RAG / A2A)
    WORKDAY_API_BASE_URL: str = "https://api.workday.com/v40"
    WORKDAY_CLIENT_ID: Optional[str] = None
    WORKDAY_CLIENT_SECRET: Optional[str] = None
    
    SERVICENOW_API_BASE_URL: str = "https://instance.service-now.com/api/now"
    SERVICENOW_CLIENT_ID: Optional[str] = None
    SERVICENOW_CLIENT_SECRET: Optional[str] = None
    
    VERTEX_SEARCH_DATASTORE_ID: Optional[str] = None
    A2A_PUBSUB_TOPIC: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")



@lru_cache()
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
