"""
Unit & Integration Test Suite for ServiceImmediately ITSM MCP Client & Agent Node.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §5.1, §5.3, §5.9 (FR-4.1 - FR-4.3, NFR-4.1, UC-1.3).
"""

import asyncio
import unittest

from app.adapters.itsm_client import (
    DuplicateIncidentError,
    InvalidStateTransitionError,
    PriorityVerificationError,
    ServiceImmediatelyError,
    ServiceImmediatelyMCPClient,
)
from app.agents.itsm import ITSMSpecialistNode
from app.state import AgentState


class TestServiceImmediatelyMCPIntegration(unittest.TestCase):

    def setUp(self):
        self.mcp_credential = "mcp_5tnLwYUZ2U8717E2EfFy0Rzqy5d-izvXqAjZfQUCYBQ"
        self.client = ServiceImmediatelyMCPClient(mcp_credential=self.mcp_credential)
        self.node = ITSMSpecialistNode(mcp_client=self.client)

    def test_mcp_auth_headers(self):
        """Verifies that MCP auth headers contain the assigned credential."""
        headers = self.client.get_auth_headers(agent_id="itsm-1.4.0")
        self.assertEqual(headers["Authorization"], f"Bearer {self.mcp_credential}")
        self.assertEqual(headers["X-Agent-Origin"], "itsm-1.4.0")
        self.assertIn("elevate-itsm-mcp", headers["X-MCP-Client"])

    def test_get_incident_fr42(self):
        """FR-4.2: Query incident details and comment timeline."""
        incident = self.node.get_incident("INC-5001")
        self.assertEqual(incident["ticketId"], "INC-5001")
        self.assertEqual(incident["callerId"], "EMP-44210")
        self.assertEqual(incident["state"], "In Progress")
        self.assertTrue(len(incident["comments"]) >= 1)
        self.assertEqual(incident["comments"][0]["author"], "IT Tech")

    def test_create_incident_fr41_fr42(self):
        """FR-4.1 & FR-4.2: Auditable ticket creation with verified automation source."""
        res = self.node.create_incident(
            caller_id="EMP-44210",
            category="Hardware",
            short_description="Need replacement laptop battery",
            priority="4 - Low",
            description="Battery health is at 55%.",
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["ticketId"].startswith("REQ-"))
        self.assertEqual(res["source"], "AI_AGENT_AUTOMATION")

        # Verify created record in store
        saved = self.node.get_incident(res["ticketId"])
        self.assertEqual(saved["callerId"], "EMP-44210")
        self.assertEqual(saved["source"], "AI_AGENT_AUTOMATION")
        self.assertEqual(saved["priority"], "4 - Low")

    def test_duplicate_suppression_fr43(self):
        """FR-4.3: Duplicate mitigation suppresses duplicate tickets submitted within 10 minutes."""
        self.node.create_incident(
            caller_id="EMP-99001",
            category="Network",
            short_description="Cannot connect to corporate Wi-Fi",
            priority="3 - Moderate",
        )

        # Attempt immediate duplicate submission
        with self.assertRaises(DuplicateIncidentError):
            self.node.create_incident(
                caller_id="EMP-99001",
                category="Network",
                short_description="Cannot connect to corporate Wi-Fi",
                priority="3 - Moderate",
            )

    def test_priority_verification_fr43(self):
        """FR-4.3: Enforce alignment between Critical priority and justification."""
        # Case A: 1 - Critical without justification -> Rejected
        with self.assertRaises(PriorityVerificationError):
            self.node.create_incident(
                caller_id="EMP-44210",
                category="Software",
                short_description="Font size looks small in app",
                priority="1 - Critical",
                description="Minor aesthetic preference",
            )

        # Case B: 1 - Critical with valid outage justification -> Accepted
        res = self.node.create_incident(
            caller_id="EMP-44210",
            category="Infrastructure",
            short_description="Global payroll portal down with 500 error",
            priority="1 - Critical",
            description="System down widespread outage affecting North America.",
        )
        self.assertEqual(res["status"], "SUCCESS")
        saved = self.node.get_incident(res["ticketId"])
        self.assertEqual(saved["priority"], "1 - Critical")

    def test_state_transitions_fr43(self):
        """FR-4.3: Validate lifecycle state transition legality."""
        res = self.node.create_incident(
            caller_id="EMP-44210",
            category="Hardware",
            short_description="Monitor flickering",
            priority="4 - Low",
        )
        ticket_id = res["ticketId"]

        # Illegal skip: New directly to Closed
        with self.assertRaises(InvalidStateTransitionError):
            self.client.update_status(ticket_id=ticket_id, state="Closed")

        # Legal progression: New -> In Progress -> Resolved -> Closed
        s1 = self.node.update_status(ticket_id=ticket_id, state="In Progress")
        self.assertEqual(s1["currentState"], "In Progress")

        s2 = self.node.update_status(ticket_id=ticket_id, state="Resolved", resolution_notes="Cable replaced.")
        self.assertEqual(s2["currentState"], "Resolved")

        s3 = self.node.update_status(ticket_id=ticket_id, state="Closed")
        self.assertEqual(s3["currentState"], "Closed")

    def test_post_comment_fr42(self):
        """FR-4.2: Post updates to activity timeline."""
        res = self.node.post_comment(
            ticket_id="INC-5001",
            author="Sarah Chen",
            body="Rebooting router resolved the issue temporarily.",
        )
        self.assertEqual(res["status"], "SUCCESS")

        incident = self.node.get_incident("INC-5001")
        self.assertEqual(len(incident["comments"]), 2)
        self.assertEqual(incident["comments"][-1]["author"], "Sarah Chen")


class TestITSMAgentExecution(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.node = ITSMSpecialistNode()

    async def test_execute_lookup_uc13(self):
        """UC-1.3: Natural language lookup of existing ticket INC-5001."""
        state: AgentState = {
            "session_id": "s-1",
            "employee_id": "EMP-44210",
            "user_input": "What is the status of ticket INC-5001?",
            "masked_input": "What is the status of ticket INC-5001?",
        }
        res = await self.node.execute(state)
        self.assertIn("INC-5001", res["final_response"])
        self.assertIn("In Progress", res["final_response"])
        self.assertEqual(res["next_node"], "guardrails_out")

    async def test_execute_create_ticket(self):
        """UC-1.3: Natural language request to open a ticket."""
        state: AgentState = {
            "session_id": "s-2",
            "employee_id": "EMP-44210",
            "user_input": "Please create ticket because my VPN connection keeps dropping.",
            "masked_input": "Please create ticket because my VPN connection keeps dropping.",
        }
        res = await self.node.execute(state)
        self.assertIn("Support incident", res["final_response"])
        self.assertIn("created with priority 3 - Moderate", res["final_response"])

    async def test_execute_graceful_duplicate_handling_nfr41(self):
        """NFR-4.1: Graceful non-technical handling when duplicate ticket is triggered."""
        state: AgentState = {
            "session_id": "s-3",
            "employee_id": "EMP-44210",
            "user_input": "open ticket VPN connection keeps dropping",
            "masked_input": "open ticket VPN connection keeps dropping",
        }
        # First attempt
        await self.node.execute(dict(state))

        # Duplicate attempt immediately
        res2 = await self.node.execute(dict(state))
        self.assertIn("identical details was recently submitted", res2["final_response"])
        self.assertNotIn("Traceback", res2["final_response"])


if __name__ == "__main__":
    unittest.main()
