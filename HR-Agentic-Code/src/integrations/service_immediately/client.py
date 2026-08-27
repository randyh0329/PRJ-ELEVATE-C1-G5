"""ServiceImmediately ITSM client adapter with guardrails, audit logging, and FastMCP integration."""
import datetime
import logging
from typing import Dict, List, Optional
from config.settings import get_settings
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
from src.integrations.mcp.client import SaaSFastMCPClient, saas_fast_mcp_client
from src.guardrails.operation_guardrails import OperationGuardrailEngine, guardrail_engine
from src.telemetry.audit_logger import AuditLogger, audit_logger

logger = logging.getLogger("integrations.service_immediately")


class ServiceImmediatelyClient:
    """Enterprise client adapter for ServiceImmediately ITSM/HRSD operations (FastMCP + Hybrid Fallback)."""

    def __init__(
        self,
        service: Optional[ServiceImmediatelyMockService] = None,
        mcp_client: Optional[SaaSFastMCPClient] = None,
        guardrails: Optional[OperationGuardrailEngine] = None,
        logger: Optional[AuditLogger] = None,
        origin: str = "HR_AGENT_ORCHESTRATOR_V1"
    ) -> None:
        self._service = service or service_immediately_mock_service
        self._mcp_client = mcp_client or saas_fast_mcp_client
        self._guardrails = guardrails or guardrail_engine
        self._logger = logger or audit_logger
        self._origin = origin
        self._use_live_mcp = getattr(get_settings(), "USE_LIVE_MCP", True)

    def _should_use_live_mcp(self, employee_id: str) -> bool:
        """Determines if the target employee should be routed to live FastMCP."""
        if not self._use_live_mcp or not self._mcp_client:
            return False
        if employee_id == "EMP-509":
            return True
        try:
            return employee_id == self._mcp_client.get_current_employee_id()
        except Exception:
            return False

    def list_tickets_for_user(self, caller_employee_id: str) -> List[IncidentTicket]:
        """List tickets created by or assigned to the caller."""
        if self._should_use_live_mcp(caller_employee_id):
            try:
                mcp_tickets = self._mcp_client.list_tickets(caller_employee_id)
                tickets = []
                for t in mcp_tickets:
                    tickets.append(IncidentTicket(
                        ticket_id=t.get("ticket_id", "INC0001000"),
                        requester_id=t.get("requested_by", caller_employee_id),

                        category=t.get("category", "General"),
                        priority=t.get("priority", "3 - Moderate"),
                        status=t.get("status", "New"),
                        short_description=t.get("short_description", "IT Ticket"),
                        created_at=t.get("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
                    ))
                return tickets
            except Exception as e:
                logger.warning(f"Live ServiceImmediately FastMCP list_tickets failed: {e}. Falling back to mock service.")
        return self._service.list_tickets_for_user(caller_employee_id)

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
        existing = [t.model_dump() for t in self.list_tickets_for_user(caller_employee_id)]
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

        ticket = None
        if self._should_use_live_mcp(caller_employee_id):
            try:
                res = self._mcp_client.create_ticket(
                    requested_by=caller_employee_id,
                    category=category,
                    short_description=short_description,
                    priority=assigned_prio
                )
                tid = "INC0009999"
                if isinstance(res, dict):
                    tid = res.get("structuredContent", {}).get("result") or res.get("ticket_id") or "INC0009999"
                    if "content" in res and isinstance(res["content"], list) and len(res["content"]) > 0:
                        text = res["content"][0].get("text", "")
                        if "INC" in text:
                            for word in text.split():
                                if word.startswith("INC"):
                                    tid = word
                                    break
                ticket = IncidentTicket(
                    ticket_id=str(tid),
                    requester_id=caller_employee_id,
                    category=category,
                    priority=assigned_prio,
                    short_description=short_description,
                    status="New"
                )
            except Exception as e:
                logger.warning(f"Live ServiceImmediately FastMCP create_ticket failed: {e}. Falling back to mock service.")
                ticket = self._service.create_incident(
                    requester_id=caller_employee_id,
                    category=category,
                    priority=assigned_prio,
                    short_description=short_description,
                    origin=self._origin
                )
        else:
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
            details={
                "ticket_id": ticket.ticket_id,
                "priority": ticket.priority,
                "category": ticket.category,
            }
        )
        return ticket

    def add_comment(self, caller_employee_id: str, ticket_id: str, comment_text: str) -> TicketComment:
        """Add timeline comment with audit attribution."""
        comment = None
        if self._should_use_live_mcp(caller_employee_id):
            try:
                self._mcp_client.add_ticket_comment(ticket_id=ticket_id, author=caller_employee_id, comment=comment_text)
                comment = TicketComment(
                    ticket_id=ticket_id,
                    author=caller_employee_id,
                    comment_text=comment_text
                )
            except Exception as e:
                logger.warning(f"Live ServiceImmediately FastMCP add_comment failed: {e}. Falling back to mock service.")
                comment = self._service.add_comment(ticket_id, caller_employee_id, comment_text)
        else:
            comment = self._service.add_comment(ticket_id, caller_employee_id, comment_text)

        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_ADD_COMMENT",
            status="SUCCESS",
            details={"ticket_id": ticket_id}
        )
        return comment

    def update_incident_status(
        self,
        caller_employee_id: str,
        ticket_id: str,
        new_status: str,
        resolution_notes: str = ""
    ) -> IncidentTicket:
        """Update ticket lifecycle status enforcing valid state transitions."""
        current_ticket = self.get_ticket_details(caller_employee_id, ticket_id)
        if current_ticket:
            trans_res = self._guardrails.validate_status_transition(current_ticket.status, new_status)
            if not trans_res.is_valid:
                self._logger.log_event(
                    caller_employee_id=caller_employee_id,
                    action_type="SERVICE_IMMEDIATELY_UPDATE_STATUS",
                    status="REFUSED",
                    details={"error": trans_res.error_message, "rule": trans_res.rule_name}
                )
                raise ValueError(trans_res.error_message)

        if self._should_use_live_mcp(caller_employee_id):
            try:
                self._mcp_client.update_ticket_status(
                    ticket_id=ticket_id,
                    status=new_status,
                    resolution_notes=resolution_notes,
                    updated_by=caller_employee_id
                )
            except Exception as e:
                logger.warning(f"Live ServiceImmediately FastMCP update_status failed: {e}.")


        updated = self._service.update_status(ticket_id, new_status, resolution_notes)
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_UPDATE_STATUS",
            status="SUCCESS" if updated else "FAILED",
            details={"ticket_id": ticket_id, "new_status": new_status}
        )
        return updated or current_ticket

    def create_hardware_request(
        self,
        caller_employee_id: str,
        item: str,
        shipping_address: str,
        referenced_policy_section: str = "Sec 08.3"
    ) -> HardwareRequest:
        """Submit a hardware procurement request."""
        req = self._service.create_hardware_request(
            requester_id=caller_employee_id,
            item=item,
            shipping_address=shipping_address,
            referenced_policy_section=referenced_policy_section
        )
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_REQUEST_HARDWARE",
            status="SUCCESS",
            details={"request_id": req.request_id, "item": req.item}
        )
        return req

    def create_facilities_ticket(
        self,
        caller_employee_id: str,
        category: str,
        office: str,
        start_date: str
    ) -> FacilitiesTicket:
        """Submit a facilities transfer or badge request."""
        ticket = self._service.create_facilities_ticket(
            category=category,
            office=office,
            start_date=start_date
        )
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_REQUEST_FACILITIES",
            status="SUCCESS",
            details={"ticket_id": ticket.ticket_id, "office": office}
        )
        return ticket

    def request_hardware(
        self,
        caller_employee_id: str,
        item: str,
        justification: str,
        category: str = "Hardware"
    ) -> HardwareRequest:
        """Submit a hardware procurement request."""
        req = self._service.create_hardware_request(caller_employee_id, item, justification, category)
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_REQUEST_HARDWARE",
            status="SUCCESS",
            details={"request_id": req.request_id, "item": req.item}
        )
        return req

    def request_facilities(
        self,
        caller_employee_id: str,
        target_office: str,
        description: str,
        category: str = "Facilities"
    ) -> FacilitiesTicket:
        """Submit a facilities transfer or badge request."""
        ticket = self._service.create_facilities_ticket(caller_employee_id, target_office, description, category)
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_REQUEST_FACILITIES",
            status="SUCCESS",
            details={"ticket_id": ticket.ticket_id, "office": target_office}
        )
        return ticket


    def cancel_ticket(self, caller_employee_id: str, ticket_id: str, reason: str = "Saga Compensating Action") -> bool:
        """Compensating action: Cancel or close an errant incident ticket."""
        success = self._service.cancel_ticket(ticket_id)
        self._logger.log_event(
            caller_employee_id=caller_employee_id,
            action_type="SERVICE_IMMEDIATELY_CANCEL_TICKET",
            status="COMPENSATED" if success else "FAILED",
            details={"ticket_id": ticket_id, "reason": reason}
        )
        return success

    def create_escalated_incident(self, priority: str, description: str) -> IncidentTicket:
        """System action: Create an unblockable human review escalation ticket."""
        return self._service.create_escalated_incident(priority, description)


# Global singleton client
service_immediately_client = ServiceImmediatelyClient()
