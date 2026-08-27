"""Data models for WorkWeek HCM operations."""
from typing import Optional
from pydantic import BaseModel, Field


class EmployeeProfile(BaseModel):
    """Employee demographic and employment profile."""
    employee_id: str
    full_name: str
    email: str
    phone_number: str
    home_address: str
    work_location_status: str  # e.g., 'REMOTE_FULL_TIME', 'HYBRID', 'ONSITE'
    current_office: str
    country: str
    job_title: str
    manager_id: str
    is_active: bool = True


class LeaveBalances(BaseModel):
    """Employee accrued and remaining leave balances."""
    employee_id: str
    vacation_accrued: float
    vacation_used: float
    vacation_remaining: float
    sick_accrued: float
    sick_used: float
    sick_remaining: float


class LeaveRequest(BaseModel):
    """Leave submission payload and record."""
    request_id: str
    employee_id: str
    leave_type: str  # 'Vacation', 'Sick', 'Sick_LOA', 'Bereavement'
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    days: float
    status: str = "SUBMITTED"  # SUBMITTED, APPROVED, CANCELLED
    submitted_at: str
    origin: str = "HR_AGENT_ORCHESTRATOR_V1"


class LeaveSubmissionResponse(BaseModel):
    """Result of leave submission."""
    success: bool
    request_id: Optional[str] = None
    message: str
    remaining_balance: Optional[float] = None


class ContactUpdateResponse(BaseModel):
    """Result of updating contact info."""
    success: bool
    employee_id: str
    message: str
    updated_fields: dict
