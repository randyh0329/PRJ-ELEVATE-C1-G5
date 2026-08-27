from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from src.models.common import CompensationClassEnum


class SagaStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stepIndex: int
    targetSystem: str
    action: str
    compensationClass: CompensationClassEnum
    status: str = Field(..., description="PENDING | SUCCESS | FAILED_HANDED_TO_HUMAN | COMPENSATED")
    externalReferenceId: Optional[str] = None
    followUpRef: Optional[str] = None
    compensationPayload: Optional[Dict[str, Any]] = None
    timestamp: str


class SagaRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., alias="_id")
    sessionId: str
    employeeId: str
    workflowType: str
    currentState: str = Field(..., description="RUNNING | COMPLETED | PARTIALLY_COMPLETED_MANUAL_FOLLOWUP | COMPENSATED_ROLLED_BACK")
    steps: List[SagaStep] = Field(default_factory=list)
    ttl_expiry: str
