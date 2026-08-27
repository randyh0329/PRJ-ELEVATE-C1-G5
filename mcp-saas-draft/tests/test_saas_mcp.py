import sys
from pathlib import Path

# Add mcp-saas-draft directory to sys.path
MCP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_DIR))

import pytest
from src.saas_mcp_client import SaaSMCPClient

from src.adk_tools import (
    get_current_employee_id,
    get_employee_balances,
    get_personal_info,
    get_leave_requests,
    list_tickets,
    WORKWEEK_ADK_TOOLS,
    ITSM_ADK_TOOLS,
    ALL_SAAS_ADK_TOOLS
)


def test_mcp_client_headers_custom_x_token():
    client = SaaSMCPClient(
        base_url="https://mock-saas.aishprabhat.demo.altostrat.com",
        mcp_token="mcp_HiIwlFkRL-DrjYgdQvO-fMHg8Q8A_YskI5J00qrP8SA"
    )
    headers = client._get_headers()
    assert headers["X-MCP-Token"] == "mcp_HiIwlFkRL-DrjYgdQvO-fMHg8Q8A_YskI5J00qrP8SA"
    assert "Authorization" not in headers
    assert "application/json" in headers["Accept"]


@pytest.mark.asyncio
async def test_live_workweek_mcp_tools():
    # 1. Resolve employee id
    eid_res = await get_current_employee_id()
    eid = eid_res.get("structuredContent", {}).get("result") or eid_res.get("content", [{}])[0].get("text")
    assert eid == "EMP-509"

    # 2. Live balances
    balances = await get_employee_balances(eid)
    text = balances.get("content", [{}])[0].get("text", "")
    assert "Vacation" in text
    assert "Sick" in text

    # 3. Personal info
    info = await get_personal_info(eid)
    info_text = info.get("content", [{}])[0].get("text", "")
    assert "Singapore" in info_text


@pytest.mark.asyncio
async def test_live_itsm_mcp_tools():
    # List live tickets for EMP-509
    tickets = await list_tickets("EMP-509")
    text = tickets.get("content", [{}])[0].get("text", "")
    assert "INC0003359" in text or "INC" in text
    assert "Romij Employee" in text


def test_adk_tool_registries():
    assert len(WORKWEEK_ADK_TOOLS) == 7
    assert len(ITSM_ADK_TOOLS) == 4
    assert len(ALL_SAAS_ADK_TOOLS) == 11

    for tool_fn in ALL_SAAS_ADK_TOOLS:
        assert callable(tool_fn)
        assert tool_fn.__doc__ is not None and len(tool_fn.__doc__.strip()) > 10
