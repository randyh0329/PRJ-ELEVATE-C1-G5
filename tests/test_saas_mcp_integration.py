"""
Integration tests for HR-Agentic-Code with live SaaS FastMCP endpoints.
Validates WorkWeek HCM and ServiceImmediately ITSM live communication via X-MCP-Token header.
"""

import pytest

from config.settings import get_settings
from src.integrations.mcp.client import SaaSFastMCPClient
from src.integrations.service_immediately.client import ServiceImmediatelyClient
from src.integrations.workweek.client import WorkWeekClient


class TestSaaSFastMCPIntegration:
    """Test suite for FastMCP integration in HR-Agentic-Code."""

    def test_mcp_client_headers_custom_x_token(self):
        client = SaaSFastMCPClient()
        headers = client._get_headers()
        assert "X-MCP-Token" in headers
        assert headers["X-MCP-Token"] == get_settings().SAAS_MCP_CREDENTIAL
        # CRITICAL SDD RULE: No standard Authorization header allowed!
        assert "Authorization" not in headers

    def test_workweek_client_live_balance_and_profile(self):
        ww_client = WorkWeekClient()
        # 1. Resolve employee id with live token
        try:
            res = ww_client._mcp_client.call_tool_sync("work-week/mcp/", "get_current_employee_id", {})
            eid = res.get("content", [{}])[0].get("text", "")
            if eid != "EMP-509":
                pytest.skip(f"Live FastMCP token bound to {eid}, not EMP-509")
        except Exception as e:
            pytest.skip(f"Live FastMCP SaaS token expired or unauthorized: {e}")

        # 2. Get profile for EMP-509
        profile = ww_client.get_employee_profile(caller_employee_id=eid, target_employee_id=eid)

        assert profile is not None
        assert profile.employee_id == eid
        assert profile.home_address is not None

        # 3. Get balances
        balances = ww_client.get_leave_balances(caller_employee_id=eid, target_employee_id=eid)
        assert balances is not None
        assert balances.vacation_remaining > 0
        assert balances.sick_remaining > 0



    def test_service_immediately_client_live_ticket_list(self):
        sn_client = ServiceImmediatelyClient()
        eid = "EMP-509"
        try:
            tickets = sn_client._mcp_client.list_tickets(eid)
        except Exception as e:
            pytest.skip(f"Live FastMCP SaaS token expired or unauthorized: {e}")
        tickets = sn_client.list_tickets_for_user(caller_employee_id=eid)
        assert isinstance(tickets, list)
        assert len(tickets) >= 1
        ticket_ids = [t.ticket_id for t in tickets]
        assert "INC0003359" in ticket_ids or any(tid.startswith("INC") for tid in ticket_ids)

