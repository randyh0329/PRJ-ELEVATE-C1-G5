"""WorkWeek HCM client adapter with security checks and operational guardrails."""
import datetime
from typing import Optional
from src.integrations.workweek.models import (
    EmployeeProfile,
    LeaveBalances,
    LeaveSubmissionResponse,
    ContactUpdateResponse,
)
from src.integrations.workweek.mock_service import WorkWeekMockService, workweek_mock_service
from src.guardrails.operation_guardrails import OperationGuardrailEngine, guardrail_engine
from src.telemetry.audit_logger import AuditLogger, audit_logger


class WorkWeekClient:
    """Enterprise client adapter for WorkWeek HCM operations."""

    def __init__(
        self,
        service: Optional[WorkWeekMockService] = None,
        guardrails: Optional[OperationGuardrailEngine] = None,
        logger: Optional[AuditLogger] = None,
        origin: str = "HR_AGENT_ORCHESTRATOR_V1"
    ) -> None:
        self._service = service or workweek_mock_service
        self._guardrails = guardrails or guardrail_engine
        self._logger = logger or audit_logger
        self._origin = origin

    def get_employee_profile(self, caller_employee_id: str, target_employee_id: str) -> Optional[EmployeeProfile]:
        """Fetch employee profile enforcing caller isolation."""
        if caller_employee_id != target_employee_id:
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="WORKWEEK_GET_PROFILE",
                status="REFUSED",
                details={"target_employee_id": target_employee_id, "reason": "Cross-employee lookup forbidden (FR-1.5)"}
            )
            raise PermissionError(f"Access Denied: Caller {caller_employee_id} cannot access profile of {target_employee_id}.")

        profile = self._service.get_profile(target_employee_id)
        status = "SUCCESS" if profile else "NOT_FOUND"
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="WORKWEEK_GET_PROFILE",
            status=status,
            details={"target_employee_id": target_employee_id}
        )
        return profile

    def get_leave_balances(self, caller_employee_id: str, target_employee_id: str) -> Optional[LeaveBalances]:
        """Fetch real-time leave balances enforcing caller isolation."""
        if caller_employee_id != target_employee_id:
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="WORKWEEK_GET_BALANCES",
                status="REFUSED",
                details={"target_employee_id": target_employee_id, "reason": "Cross-employee lookup forbidden"}
            )
            raise PermissionError(f"Access Denied: Caller {caller_employee_id} cannot access balances of {target_employee_id}.")

        balances = self._service.get_balances(target_employee_id)
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="WORKWEEK_GET_BALANCES",
            status="SUCCESS" if balances else "NOT_FOUND",
            details={"target_employee_id": target_employee_id}
        )
        return balances

    def update_contact_info(
        self,
        caller_employee_id: str,
        target_employee_id: str,
        home_address: Optional[str] = None,
        phone_number: Optional[str] = None,
        current_office: Optional[str] = None,
        country: Optional[str] = None
    ) -> ContactUpdateResponse:
        """Update contact details after passing syntax and security guardrails."""
        if caller_employee_id != target_employee_id:
            raise PermissionError("Cross-employee profile modification is strictly prohibited.")

        guard_res = self._guardrails.validate_contact_update(phone_number, home_address)
        if not guard_res.is_valid:
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="WORKWEEK_UPDATE_CONTACT",
                status="FAILED",
                details={"error": guard_res.error_message, "rule": guard_res.rule_name}
            )
            return ContactUpdateResponse(
                success=False,
                employee_id=target_employee_id,
                message=guard_res.error_message or "Validation failed",
                updated_fields={}
            )

        res = self._service.update_contact(
            employee_id=target_employee_id,
            home_address=home_address,
            phone_number=phone_number,
            current_office=current_office,
            country=country
        )
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="WORKWEEK_UPDATE_CONTACT",
            status="SUCCESS" if res.success else "FAILED",
            details={"updated_fields": res.updated_fields}
        )
        return res

    def submit_leave_request(
        self,
        caller_employee_id: str,
        target_employee_id: str,
        leave_type: str,
        start_date: datetime.date,
        end_date: datetime.date,
        days: float,
        reference_date: Optional[datetime.date] = None
    ) -> LeaveSubmissionResponse:
        """Submit a leave request after validating balance and temporal guardrails."""
        if caller_employee_id != target_employee_id:
            raise PermissionError("Cannot submit leave on behalf of another employee.")

        balances = self._service.get_balances(target_employee_id)
        if not balances:
            return LeaveSubmissionResponse(success=False, message="Employee balance record not found.")

        remaining = balances.vacation_remaining if "vacation" in leave_type.lower() else balances.sick_remaining
        guard_res = self._guardrails.validate_leave_request(
            days_requested=days,
            remaining_balance=remaining,
            start_date=start_date,
            end_date=end_date,
            reference_date=reference_date
        )

        if not guard_res.is_valid:
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="WORKWEEK_SUBMIT_LEAVE",
                status="FAILED",
                details={"error": guard_res.error_message, "rule": guard_res.rule_name}
            )
            return LeaveSubmissionResponse(
                success=False,
                message=guard_res.error_message or "Guardrail validation failed."
            )

        res = self._service.submit_leave(
            employee_id=target_employee_id,
            leave_type=leave_type,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            days=days,
            origin=self._origin
        )
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="WORKWEEK_SUBMIT_LEAVE",
            status="SUCCESS" if res.success else "FAILED",
            details={"request_id": res.request_id, "days": days, "type": leave_type}
        )
        return res

    def cancel_leave_request(self, caller_employee_id: str, request_id: str) -> bool:
        """Compensating action: Cancel a previously submitted leave request."""
        success = self._service.cancel_leave(request_id)
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="WORKWEEK_CANCEL_LEAVE",
            status="COMPENSATED" if success else "FAILED",
            details={"request_id": request_id}
        )
        return success


# Global singleton client
workweek_client = WorkWeekClient()
