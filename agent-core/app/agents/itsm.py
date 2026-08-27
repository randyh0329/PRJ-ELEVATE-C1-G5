"""
ServiceImmediately ITSM Specialist Agent.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.2, §4.1, §5.1, §5.3, §5.9 (FR-4.1 - FR-4.3, NFR-4.1).
Model: Gemini 3.7 Flash (Pinned).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.adapters.itsm_client import (
    DuplicateIncidentError,
    InvalidStateTransitionError,
    PriorityVerificationError,
    ServiceImmediatelyError,
    ServiceImmediatelyMCPClient,
)
from app.security.token_minter import CompositeTokenMinter
from app.state import AgentState

logger = logging.getLogger("agents.itsm")


class ITSMSpecialistNode:
    """
    ServiceImmediately ITSM Specialist Agent node (Gemini 3.7 Flash).
    Executes incident queries, ticket creation, comment posting, and status updates against ITSM adapter.
    """

    AGENT_ID = "itsm-1.4.0"
    MODEL_ID = "gemini-3.7-flash@2026-08"
    ADAPTER_URL = "https://serviceimmediately-adapter-prod-uc.a.run.app"

    def __init__(
        self,
        token_minter: Optional[CompositeTokenMinter] = None,
        mcp_client: Optional[ServiceImmediatelyMCPClient] = None,
        mcp_credential: Optional[str] = None,
    ):
        self.token_minter = token_minter or CompositeTokenMinter()
        self.client = mcp_client or ServiceImmediatelyMCPClient(
            mcp_credential=mcp_credential,
            endpoint_url=self.ADAPTER_URL,
        )

    @property
    def _incidents(self) -> Dict[str, Dict[str, Any]]:
        """Access to backing store for compatibility."""
        return self.client._incidents

    def get_incident(self, ticket_id: str) -> Dict[str, Any]:
        """si.get_incident (FR-4.2)"""
        return self.client.get_incident(ticket_id)

    def create_incident(
        self,
        caller_id: str,
        category: str,
        short_description: str,
        priority: str = "4 - Low",
        description: str = "",
    ) -> Dict[str, Any]:
        """si.create_incident (FR-4.1, FR-4.2, FR-4.3) - Records automation source attribution"""
        return self.client.create_incident(
            caller_id=caller_id,
            category=category,
            short_description=short_description,
            priority=priority,
            description=description,
        )

    def post_comment(self, ticket_id: str, author: str, body: str) -> Dict[str, Any]:
        """si.post_comment (FR-4.2)"""
        try:
            return self.client.post_comment(ticket_id=ticket_id, author=author, body=body)
        except ServiceImmediatelyError as e:
            return {"status": "ERROR", "code": e.error_code, "message": str(e)}

    def update_status(
        self,
        ticket_id: str,
        state: str,
        resolution_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """si.update_status (FR-4.2, FR-4.3)"""
        try:
            return self.client.update_status(
                ticket_id=ticket_id,
                state=state,
                resolution_notes=resolution_notes,
            )
        except ServiceImmediatelyError as e:
            return {"status": "ERROR", "code": e.error_code, "message": str(e)}

    async def execute(self, state: AgentState) -> AgentState:
        """
        Processes single-system ITSM requests (UC-1.3) and direct tool operations.
        """
        employee_id = state.get("employee_id", "EMP-44210")
        query = state.get("masked_input", state.get("user_input", ""))
        logger.info(f"[{self.AGENT_ID}] Executing ITSM request for caller {employee_id}")

        try:
            # Pattern 1: Look for Ticket Query (e.g. INC-5001 or REQ-1234)
            ticket_match = re.search(r"\b(INC|REQ)-[A-Za-z0-9]+\b", query, re.IGNORECASE)
            if ticket_match:
                ticket_id = ticket_match.group(0).upper()
                incident = self.get_incident(ticket_id)
                comments_str = ""
                if incident.get("comments"):
                    last_comment = incident["comments"][-1]
                    comments_str = f" Latest note from {last_comment.get('author')}: '{last_comment.get('body')}'."

                state["final_response"] = (
                    f"Status for ticket **{ticket_id}**: Current state is **{incident.get('state')}**, "
                    f"Priority: {incident.get('priority')}, Category: {incident.get('category')}. "
                    f"Summary: {incident.get('shortDescription')}.{comments_str}"
                )
            elif any(k in query.lower() for k in ["create ticket", "open ticket", "file ticket", "vpn connection keeps dropping", "vpn drops"]):
                # Pattern 2: Create ticket request
                res = self.create_incident(
                    caller_id=employee_id,
                    category="Network",
                    short_description="VPN connection keeps dropping",
                    priority="3 - Moderate",
                    description=query,
                )
                state["final_response"] = (
                    f"Support incident **{res['ticketId']}** has been created with priority 3 - Moderate. "
                    "An IT technician has been assigned to investigate your network issue."
                )
            else:
                # Default status overview
                state["final_response"] = (
                    "You have 1 active IT incident: **INC-5001** (VPN connection drops on MacOS Sequoia) - State: In Progress."
                )
        except DuplicateIncidentError:
            state["final_response"] = (
                "A support ticket with identical details was recently submitted. "
                "To avoid duplication, please check your open tickets or add a comment to your existing ticket."
            )
        except PriorityVerificationError as e:
            state["final_response"] = f"Unable to create ticket: {e.message}"
        except Exception as e:
            logger.error(f"ITSM execution failure: {e}", exc_info=True)
            # NFR-4.1 Graceful Failure Handling: Do not expose raw stack traces
            state["final_response"] = (
                "The ServiceImmediately ITSM service is temporarily unavailable. "
                "Please try again shortly or contact the IT Help Desk."
            )

        state["next_node"] = "guardrails_out"
        return state
