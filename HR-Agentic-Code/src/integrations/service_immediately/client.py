"""ServiceImmediately ITSM client adapter with guardrails and audit logging."""
import datetime
from typing import Dict, List, Optional
from src.integrations.service_immediately.models import (
    IncidentTicket,
    TicketComment,
    HardwareRequest,
    FacilitiesTicket,
)
from src.integrations.service_immediately.mock_service import (
    ServiceImmediatelyMockService,
    service_immediately_mock_service,
)
from src.guardrails.operation_guardrails import OperationGuardrailEngine, guardrail_engine
from src.telemetry.audit_logger import AuditLogger, audit_logger


class ServiceImmediatelyClient:
    """Enterprise client adapter for ServiceImmediately ITSM/HRSD operations."""

    def __init__(
        self,
        service: Optional[ServiceImmediatelyMockService] = None,
        guardrails: Optional[OperationGuardrailEngine] = None,
        logger: Optional[AuditLogger] = None,
        origin: str = "HR_AGENT_ORCHESTRATOR_V1"
    ) -> None:
        self._service = service or service_immediately_mock_service
        self._guardrails = guardrails or guardrail_engine
        self._logger = logger or audit_logger
        self._origin = origin

    def get_ticket_details(self, caller_employee_id: str, ticket_id: str) -> Optional[IncidentTicket]:
        """Fetch incident ticket details."""
        ticket = self._service.get_ticket(ticket_id)
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_GET_TICKET",
            status="SUCCESS" if ticket else "NOT_FOUND",
            details={"ticket_id": ticket_id}
        )
        return ticket

    def create_incident_ticket(
        self,
        caller_employee_id: str,
        category: str,
        requested_priority: str,
        short_description: str,
        now: Optional[datetime.datetime] = None
    ) -> IncidentTicket:
        """Create a new support incident ticket after validating deduplication and priority rules."""
        # 1. Check deduplication guardrail
        existing = [t.model_dump() for t in self._service.list_tickets_for_user(caller_employee_id)]
        dedup_res = self._guardrails.validate_ticket_deduplication(
            requester_id=caller_employee_id,
            category=category,
            existing_tickets=existing,
            window_minutes=30,
            now=now
        )
        if not dedup_res.is_valid:
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="SERVICE_IMMEDIATELY_CREATE_INCIDENT",
                status="REFUSED",
                details={"reason": dedup_res.error_message, "rule": dedup_res.rule_name}
            )
            raise ValueError(dedup_res.error_message)

        # 2. Verify priority
        assigned_prio = self._guardrails.verify_priority_assignment(
            category=category,
            description=short_description,
            requested_priority=requested_priority
        )

        try:
            ticket = self._service.create_incident(
                requester_id=caller_employee_id,
                category=category,
                priority=assigned_prio,
                short_description=short_description,
                origin=self._origin
            )
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="SERVICE_IMMEDIATELY_CREATE_INCIDENT",
                status="SUCCESS",
                details={"ticket_id": ticket.ticket_id, "priority": assigned_prio, "category": category}
            )
            return ticket
        except Exception as e:
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="SERVICE_IMMEDIATELY_CREATE_INCIDENT",
                status="FAILED",
                details={"error": str(e), "category": category}
            )
            raise

    def post_ticket_comment(
        self,
        caller_employee_id: str,
        ticket_id: str,
        comment_text: str
    ) -> Optional[TicketComment]:
        """Post a comment on a ticket."""
        cmt = self._service.post_comment(
            ticket_id=ticket_id,
            author_id=caller_employee_id,
            comment_text=comment_text,
            origin=self._origin
        )
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_POST_COMMENT",
            status="SUCCESS" if cmt else "FAILED",
            details={"ticket_id": ticket_id}
        )
        return cmt

    def update_ticket_status(
        self,
        caller_employee_id: str,
        ticket_id: str,
        new_status: str,
        resolution_notes: Optional[str] = None
    ) -> bool:
        """Update ticket status checking valid state transitions."""
        ticket = self._service.get_ticket(ticket_id)
        if not ticket:
            return False

        trans_res = self._guardrails.validate_ticket_transition(ticket.status, new_status)
        if not trans_res.is_valid:
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="SERVICE_IMMEDIATELY_UPDATE_STATUS",
                status="REFUSED",
                details={"error": trans_res.error_message, "current": ticket.status, "target": new_status}
            )
            raise ValueError(trans_res.error_message)

        success = self._service.update_status(ticket_id, new_status, resolution_notes)
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_UPDATE_STATUS",
            status="SUCCESS" if success else "FAILED",
            details={"ticket_id": ticket_id, "new_status": new_status}
        )
        return success

    def create_hardware_request(
        self,
        caller_employee_id: str,
        item: str,
        shipping_address: str,
        referenced_policy_section: str = "Sec 08.3"
    ) -> HardwareRequest:
        """Create hardware order ticket (UC-2.1)."""
        req = self._service.create_hardware_request(
            requester_id=caller_employee_id,
            item=item,
            shipping_address=shipping_address,
            referenced_policy_section=referenced_policy_section
        )
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_HARDWARE_REQ",
            status="SUCCESS",
            details={"request_id": req.request_id, "item": item, "address": shipping_address}
        )
        return req

    def create_facilities_ticket(
        self,
        caller_employee_id: str,
        category: str,
        office: str,
        start_date: str
    ) -> FacilitiesTicket:
        """Create facilities badge ticket (UC-2.3)."""
        ticket = self._service.create_facilities_ticket(
            category=category,
            office=office,
            start_date=start_date
        )
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_FACILITIES_REQ",
            status="SUCCESS",
            details={"ticket_id": ticket.ticket_id, "office": office, "start_date": start_date}
        )
        return ticket

    def create_escalated_incident(self, priority: str, description: str) -> IncidentTicket:
        """Create automated escalation ticket."""
        return self._service.create_escalated_incident(priority, description)


# Global singleton client
service_immediately_client = ServiceImmediatelyClient()
