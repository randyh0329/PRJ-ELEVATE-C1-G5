"""Application settings and environment configuration."""
from functools import lru_cache

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
    # Workforce calendar. Every "is this date in the past?" decision resolves
    # against this zone rather than the serving region's clock - see
    # `src.core.clock` for why that distinction is load-bearing under §2.2.
    BUSINESS_TIMEZONE: str = "Asia/Singapore"

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
    SAAS_MCP_CREDENTIAL: str = "mcp_3DpwwQTaG6eV5SJpTA-QIV7aUqDblj-Qkn8bDkeiHWk"
    USE_LIVE_MCP: bool = True
    GCP_PROJECT_ID: str = "pe-group5"
    MCP_USER_TOKENS_SECRET_ID: str = "mcp-user-tokens"
    USE_SECRET_MANAGER: bool = True

    # Model Armor Settings (§4.3, FR-1.3, NFR-1.1, NFR-2.1, ALRT-08)
    PROJECT_ID: str = "pe-group5"
    REGION: str = "us-central1"
    USE_LIVE_MODEL_ARMOR: bool = False
    MODEL_ARMOR_USER_TEMPLATE: str = "hr-ingress-template"
    MODEL_ARMOR_MODEL_TEMPLATE: str = "hr-egress-template"
    MODEL_ARMOR_DEADLINE_MS: int = 150
    MODEL_ARMOR_CIRCUIT_BREAKER_RATE: float = 0.02

    # Future Boilerplate Settings (Live SaaS / RAG / A2A)
    WORKDAY_API_BASE_URL: str = "https://api.workday.com/v40"
    WORKDAY_CLIENT_ID: str | None = None
    WORKDAY_CLIENT_SECRET: str | None = None

    SERVICENOW_API_BASE_URL: str = "https://instance.service-now.com/api/now"
    SERVICENOW_CLIENT_ID: str | None = None
    SERVICENOW_CLIENT_SECRET: str | None = None

    VERTEX_SEARCH_DATASTORE_ID: str | None = None
    A2A_PUBSUB_TOPIC: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")



@lru_cache
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
