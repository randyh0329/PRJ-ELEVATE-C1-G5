"""Cross-System Saga Coordinator implementing backward compensation and escalation ticketing."""
import datetime
import logging
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field
from src.integrations.workweek.client import WorkWeekClient, workweek_client
from src.integrations.service_immediately.client import ServiceImmediatelyClient, service_immediately_client
from src.telemetry.audit_logger import AuditLogger, audit_logger


class SagaStep(BaseModel):
    """Execution step record in a Saga distributed transaction."""
    step_name: str
    target_system: str
    action_type: str
    status: str = "PENDING"  # PENDING, COMPLETED, FAILED, COMPENSATED
    step_result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class SagaResult(BaseModel):
    """Final result of a Saga orchestrated transaction."""
    success: bool
    message: str
    steps_executed: List[SagaStep] = Field(default_factory=list)
    compensated: bool = False
    escalation_ticket_id: Optional[str] = None


class SagaCoordinator:
    """Coordinates multi-system transactions with automated backward compensation."""

    def __init__(
        self,
        ww_client: Optional[WorkWeekClient] = None,
        sn_client: Optional[ServiceImmediatelyClient] = None,
        logger: Optional[AuditLogger] = None
    ) -> None:
        self._ww_client = ww_client or workweek_client
        self._sn_client = sn_client or service_immediately_client
        self._logger = logger or audit_logger

    def execute_medical_leave_orchestration(
        self,
        caller_employee_id: str,
        start_date: datetime.date,
        end_date: datetime.date,
        days: float,
        manager_id: str = "MGR-2001",
        reference_date: Optional[datetime.date] = None
    ) -> SagaResult:
        """Execute Path 5 (UC-2.2): Submit medical leave in WorkWeek + create email routing in ServiceImmediately."""
        steps: List[SagaStep] = []

        # Step 1: Submit Sick_LOA Leave in WorkWeek
        step1 = SagaStep(step_name="Submit_Medical_Leave", target_system="WorkWeek", action_type="SUBMIT_LEAVE")
        steps.append(step1)

        try:
            leave_res = self._ww_client.submit_leave_request(
                caller_employee_id=caller_employee_id,
                target_employee_id=caller_employee_id,
                leave_type="Sick_LOA",
                start_date=start_date,
                end_date=end_date,
                days=days,
                reference_date=reference_date
            )
            if not leave_res.success:
                step1.status = "FAILED"
                step1.error = leave_res.message
                return SagaResult(
                    success=False,
                    message=f"Medical leave submission failed in WorkWeek: {leave_res.message}",
                    steps_executed=steps,
                    compensated=False
                )

            step1.status = "COMPLETED"
            step1.step_result = {"request_id": leave_res.request_id, "remaining": leave_res.remaining_balance}
            leave_request_id = leave_res.request_id

        except Exception as e:
            step1.status = "FAILED"
            step1.error = str(e)
            return SagaResult(
                success=False,
                message=f"WorkWeek leave submission threw an exception: {str(e)}",
                steps_executed=steps,
                compensated=False
            )

        # Step 2: Create Email Routing Incident in ServiceImmediately
        step2 = SagaStep(step_name="Create_Access_Routing_Ticket", target_system="ServiceImmediately", action_type="CREATE_INCIDENT")
        steps.append(step2)

        try:
            sn_ticket = self._sn_client.create_incident_ticket(
                caller_employee_id=caller_employee_id,
                category="ACCESS_ROUTING",
                requested_priority="3 - Moderate",
                short_description=f"Route email access to Manager {manager_id} during Medical Leave {leave_request_id}"
            )
            step2.status = "COMPLETED"
            step2.step_result = {"ticket_id": sn_ticket.ticket_id}

            return SagaResult(
                success=True,
                message=f"Medical leave booked in WorkWeek (Ref: {leave_request_id}). ServiceImmediately ticket [{sn_ticket.ticket_id}] opened to route email access to your manager. Remember to upload your MC within 48h.",
                steps_executed=steps,
                compensated=False
            )

        except Exception as e:
            step2.status = "FAILED"
            step2.error = str(e)

            # --- BACKWARD COMPENSATION ---
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="SAGA_BACKWARD_COMPENSATION",
                status="TRIGGERED",
                details={"reason": f"Step 2 failed ({str(e)}). Rolling back Step 1 ({leave_request_id})."}
            )

            # Roll back WorkWeek leave
            if leave_request_id:
                self._ww_client.cancel_leave_request(caller_employee_id, leave_request_id)
                step1.status = "COMPENSATED"

            # Create escalated support ticket for manual PeopleOps setup
            escalation_ticket = self._sn_client.create_escalated_incident(
                priority="2 - High",
                description=f"Automated Saga rollback occurred. Manual medical leave setup required for {caller_employee_id} (WorkWeek ref {leave_request_id} was cancelled due to error: {str(e)})"
            )
            escalation_id = escalation_ticket.ticket_id

            return SagaResult(
                success=False,
                message=f"Service is temporarily unavailable while configuring email routing. Your pending leave has been rolled back to maintain consistency. Support Ticket [{escalation_id}] created for manual PeopleOps setup.",
                steps_executed=steps,
                compensated=True,
                escalation_ticket_id=escalation_id
            )


# Global singleton saga coordinator
saga_coordinator = SagaCoordinator()
