"""WorkWeek HCM integration package."""
from src.integrations.workweek.client import WorkWeekClient, workweek_client
from src.integrations.workweek.mock_service import WorkWeekMockService, workweek_mock_service
from src.integrations.workweek.models import (
    ContactUpdateResponse,
    EmployeeProfile,
    LeaveBalances,
    LeaveRequest,
    LeaveSubmissionResponse,
)

__all__ = [
    "ContactUpdateResponse",
    "EmployeeProfile",
    "LeaveBalances",
    "LeaveRequest",
    "LeaveSubmissionResponse",
    "WorkWeekClient",
    "WorkWeekMockService",
    "workweek_client",
    "workweek_mock_service",
]
