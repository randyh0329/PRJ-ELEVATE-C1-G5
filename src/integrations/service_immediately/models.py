"""Data models for ServiceImmediately ITSM/HRSD tickets and operations."""
import datetime

from pydantic import BaseModel, Field


class TicketComment(BaseModel):
    """Comment on an incident ticket."""
    comment_id: str
    author_id: str
    comment_text: str
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    origin: str = "HR_AGENT_ORCHESTRATOR_V1"


class IncidentTicket(BaseModel):
    """Support incident or request ticket."""
    ticket_id: str
    requester_id: str
    category: str  # 'IT_NETWORK', 'ACCESS_ROUTING', 'HARDWARE', 'FACILITIES', 'GENERAL_HR'
    priority: str  # '1 - Critical', '2 - High', '3 - Moderate', '4 - Low'
    short_description: str
    status: str = "New"  # 'New', 'Work in Progress', 'Pending User Info', 'Resolved', 'Closed', 'Cancelled'
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    comments: list[TicketComment] = Field(default_factory=list)
    origin: str = "HR_AGENT_ORCHESTRATOR_V1"
    metadata: dict = Field(default_factory=dict)


class HardwareRequest(BaseModel):
    """Hardware procurement request (UC-2.1)."""
    request_id: str
    requester_id: str
    item: str
    shipping_address: str
    referenced_policy_section: str
    status: str = "Approved"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class FacilitiesTicket(BaseModel):
    """Facilities access / badge ticket (UC-2.3)."""
    ticket_id: str
    category: str = "BADGE_ACCESS"
    office: str
    start_date: str
    status: str = "Submitted"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class TicketStatusUpdate(BaseModel):
    """Payload for updating ticket status."""
    ticket_id: str
    new_status: str
    resolution_notes: str | None = None
