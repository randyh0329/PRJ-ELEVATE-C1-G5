"""Pytest test fixtures and configuration."""
import pytest
from src.integrations.workweek.mock_service import workweek_mock_service
from src.integrations.service_immediately.mock_service import service_immediately_mock_service
from src.telemetry.audit_logger import audit_logger
from src.core.session import session_store
from src.core.agent import HREnterpriseAgent


@pytest.fixture(autouse=True)
def reset_system_state():
    """Reset all in-memory databases and logs before each test run."""
    workweek_mock_service.init_mock_data()
    service_immediately_mock_service.init_mock_data()
    audit_logger.clear()
    session_store.clear()
    yield


@pytest.fixture
def agent():
    """Return a clean instance of the HR Enterprise Agent."""
    return HREnterpriseAgent()
