import re
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from src.models.common import PriorityEnum, TicketStateEnum


class BusinessRulesEngine:
    @staticmethod
    def validate_leave_request(start_date_str: str, end_date_str: str, leave_type: str, work_days: float, remaining_balance: float):
        # 1. Format check
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "FORMAT_VIOLATION", "detail": "Invalid date format. Expected YYYY-MM-DD"}
            )

        today = datetime.now().date()

        # 2. Temporal Validity (FR-3.3)
        if start_dt > end_dt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "TEMPORAL_VIOLATION", "detail": "Start date must be before or equal to end date"}
            )
        if start_dt < today:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "TEMPORAL_VIOLATION", "detail": "Start date cannot be in the past"}
            )

        # 3. Balance Constraints (FR-3.3)
        if leave_type.lower() != "medical":
            requested_hours = work_days * 8.0
            if requested_hours > remaining_balance:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "INSUFFICIENT_BALANCE",
                        "detail": f"Requested {requested_hours} hours exceeds remaining accrued balance of {remaining_balance} hours"
                    }
                )

    @staticmethod
    def validate_contact_update(address: Optional[str], phone: Optional[str]):
        # Format Restrictions (FR-3.3)
        if address is not None:
            if len(address.strip()) < 5 or len(address) > 250:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "FORMAT_VIOLATION", "detail": "Address must be between 5 and 250 characters"}
                )
        if phone is not None:
            e164_regex = r"^\+?[1-9]\d{6,14}$"
            if not re.match(e164_regex, phone.strip()):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "FORMAT_VIOLATION", "detail": "Phone number must follow international E.164 format (e.g. +15551234567)"}
                )

    @staticmethod
    def validate_incident_creation(category: str, short_desc: str, priority: PriorityEnum, description: Optional[str] = None):
        # Priority Verification (FR-4.3)
        if priority == PriorityEnum.CRITICAL:
            text = f"{short_desc} {description or ''}".lower()
            critical_keywords = ["outage", "security", "safety", "sev1", "breach", "emergency", "fire", "down"]
            if not any(k in text for k in critical_keywords):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Priority verification failed. '1 - Critical' requires verified outage, security, or safety justification."
                )

    @staticmethod
    def validate_status_transition(current_state: str, target_state: str):
        # Transition Constraints (FR-4.3)
        if current_state == TicketStateEnum.NEW.value and target_state == TicketStateEnum.CLOSED.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Illegal lifecycle transition: Incident cannot transition directly from 'New' to 'Closed'. Must go through 'In Progress' or 'Resolved'."
            )
        if current_state == TicketStateEnum.CLOSED.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Illegal lifecycle transition: Incident is already 'Closed' and cannot be modified."
            )


rules_engine = BusinessRulesEngine()
