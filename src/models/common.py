from __future__ import annotations

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class PriorityEnum(str, Enum):
    CRITICAL = "1 - Critical"
    HIGH = "2 - High"
    MODERATE = "3 - Moderate"
    LOW = "4 - Low"


class TicketStateEnum(str, Enum):
    NEW = "New"
    IN_PROGRESS = "In Progress"
    ON_HOLD = "On Hold"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class LeaveTypeEnum(str, Enum):
    VACATION = "Vacation"
    SICK = "Sick"
    MEDICAL = "Medical"


class LeaveStatusEnum(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class CompensationClassEnum(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_SAFE = "REVERSIBLE_SAFE"
    ANCILLARY = "ANCILLARY"
    HUMAN_CONSEQUENTIAL = "HUMAN_CONSEQUENTIAL"


class GuardrailVerdictEnum(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REDIRECT = "REDIRECT"
