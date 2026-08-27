from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from src.models.common import LeaveTypeEnum, LeaveStatusEnum


class Balance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accruedHours: float = Field(..., description="Total accrued hours")
    usedHours: float = Field(..., description="Hours used to date")
    remainingHours: float = Field(..., description="Remaining available balance")


class EmployeeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employeeId: str = Field(..., json_schema_extra={"example": "EMP-44210"})
    name: str
    email: str
    department: str
    role: str
    manager: str
    hireDate: str
    homeAddress: Optional[str] = None
    phoneNumber: Optional[str] = None


class ContactUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    homeAddress: Optional[str] = Field(None, min_length=5, max_length=250)
    phoneNumber: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{6,14}$")


class ContactUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updated: List[str]
    previousAddress: Optional[str] = None
    previousPhone: Optional[str] = None


class BalancesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vacation: Balance
    sick: Balance


class LeaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startDate: str = Field(..., description="YYYY-MM-DD")
    endDate: str = Field(..., description="YYYY-MM-DD")
    leaveType: LeaveTypeEnum
    workDays: float = Field(..., ge=0.5)
    reason: Optional[str] = Field(None, max_length=500)


class LeaveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    leaveId: str = Field(..., json_schema_extra={"example": "LV-4021"})
    status: LeaveStatusEnum

