"""In-memory mock microservice simulating ServiceImmediately ITSM API."""
import datetime
import uuid
from typing import Dict, List, Optional
from src.integrations.service_immediately.models import (
    IncidentTicket,
    TicketComment,
    HardwareRequest,
    FacilitiesTicket,
)


class ServiceImmediatelyMockService:
    """Simulates ServiceImmediately ITSM/HRSD REST backend with deterministic state and error injection."""

    def __init__(self) -> None:
        self._tickets: Dict[str, IncidentTicket] = {}
        self._hardware_requests: Dict[str, HardwareRequest] = {}
        self._facilities_tickets: Dict[str, FacilitiesTicket] = {}
        self._simulate_500_error: bool = False
        self._ticket_counter: int = 123450
        self.init_mock_data()

    def init_mock_data(self) -> None:
        """Initialize mock database with baseline test tickets."""
        self._tickets.clear()
        self._hardware_requests.clear()
        self._facilities_tickets.clear()
        self._simulate_500_error = False
        self._ticket_counter = 123450

        # Baseline ticket for EMP-1001
        initial_ticket = IncidentTicket(
            ticket_id="INC123400",
            requester_id="EMP-1001",
            category="IT_GENERAL",
            priority="4 - Low",
            short_description="Monitor display flickers occasionally",
            status="Resolved",
            created_at=(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)).isoformat(),
            updated_at=(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
        )
        self._tickets[initial_ticket.ticket_id] = initial_ticket

    def set_simulate_error(self, simulate_error: bool) -> None:
        """Enable or disable simulated 500 server error."""
        self._simulate_500_error = simulate_error

    def create_incident(
        self,
        requester_id: str,
        category: str,
        priority: str,
        short_description: str,
        origin: str = "HR_AGENT_ORCHESTRATOR_V1",
        metadata: Optional[dict] = None
    ) -> IncidentTicket:
        """Create a new support incident ticket."""
        if self._simulate_500_error:
            raise RuntimeError("HTTP 500: ServiceImmediately database timeout - unable to process ticket.")

        self._ticket_counter += 1
        ticket_id = f"INC{self._ticket_counter}"
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        ticket = IncidentTicket(
            ticket_id=ticket_id,
            requester_id=requester_id,
            category=category,
            priority=priority,
            short_description=short_description,
            status="New",
            created_at=now_str,
            updated_at=now_str,
            origin=origin,
            metadata=metadata or {}
        )
        self._tickets[ticket_id] = ticket
        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[IncidentTicket]:
        """Fetch ticket by ID."""
        return self._tickets.get(ticket_id)

    def list_tickets_for_user(self, requester_id: str) -> List[IncidentTicket]:
        """List all tickets created by a specific user."""
        return [t for t in self._tickets.values() if t.requester_id == requester_id]

    def post_comment(
        self,
        ticket_id: str,
        author_id: str,
        comment_text: str,
        origin: str = "HR_AGENT_ORCHESTRATOR_V1"
    ) -> Optional[TicketComment]:
        """Add a comment to an existing ticket."""
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None

        comment_id = f"CMT-{uuid.uuid4().hex[:6].upper()}"
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        comment = TicketComment(
            comment_id=comment_id,
            author_id=author_id,
            comment_text=comment_text,
            created_at=now_str,
            origin=origin
        )
        ticket.comments.append(comment)
        ticket.updated_at = now_str
        return comment

    def update_status(self, ticket_id: str, new_status: str, resolution_notes: Optional[str] = None) -> bool:
        """Update ticket status."""
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return False

        ticket.status = new_status
        ticket.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if resolution_notes:
            self.post_comment(ticket_id, "SYSTEM", f"Status updated to {new_status}. Notes: {resolution_notes}")
        return True

    def create_hardware_request(
        self,
        requester_id: str,
        item: str,
        shipping_address: str,
        referenced_policy_section: str = "Sec 08.3"
    ) -> HardwareRequest:
        """Create hardware order ticket (UC-2.1)."""
        req_id = f"REQ{self._ticket_counter + 500}"
        req = HardwareRequest(
            request_id=req_id,
            requester_id=requester_id,
            item=item,
            shipping_address=shipping_address,
            referenced_policy_section=referenced_policy_section,
            status="Approved"
        )
        self._hardware_requests[req_id] = req
        return req

    def create_facilities_ticket(
        self,
        category: str,
        office: str,
        start_date: str
    ) -> FacilitiesTicket:
        """Create facilities badge provisioning ticket (UC-2.3)."""
        ticket_id = f"FAC{self._ticket_counter + 800}"
        t = FacilitiesTicket(
            ticket_id=ticket_id,
            category=category,
            office=office,
            start_date=start_date,
            status="Submitted"
        )
        self._facilities_tickets[ticket_id] = t
        return t

    def create_escalated_incident(self, priority: str, description: str) -> IncidentTicket:
        """Create escalated incident for automated Saga rollbacks."""
        return self.create_incident(
            requester_id="SYSTEM_ORCHESTRATOR",
            category="SAGA_ESCALATION",
            priority=priority,
            short_description=description,
            metadata={"type": "SAGA_COMPENSATION_ESCALATION"}
        )


# Global singleton mock service
service_immediately_mock_service = ServiceImmediatelyMockService()
