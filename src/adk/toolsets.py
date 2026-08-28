"""
ADK Toolsets and FastMCP Connectors for WorkWeek HCM, ServiceImmediately ITSM, and Policy RAG.
Compliant with Enterprise Agentic Solution Design Document §3.2 & §4.1.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from config.settings import get_settings
from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StreamableHTTPConnectionParams
from src.grounding.policy_engine import dual_grounding_engine
from src.integrations.service_immediately.client import service_immediately_client
from src.integrations.workweek.client import workweek_client

logger = logging.getLogger("adk.toolsets")


def get_workweek_mcp_toolset(credential_token: str | None = None) -> McpToolset:
    """
    Returns an ADK McpToolset connected to the WorkWeek HCM FastMCP endpoint.
    Uses custom X-MCP-Token header authentication.
    """
    settings = get_settings()
    token = credential_token or settings.SAAS_MCP_CREDENTIAL
    url = f"{settings.SAAS_MCP_BASE_URL.rstrip('/')}/workweek/mcp/"
    
    connection_params = StreamableHTTPConnectionParams(
        url=url,
        headers={"X-MCP-Token": token}
    )
    return McpToolset(connection_params=connection_params)


def get_itsm_mcp_toolset(credential_token: str | None = None) -> McpToolset:
    """
    Returns an ADK McpToolset connected to the ServiceImmediately ITSM FastMCP endpoint.
    Uses custom X-MCP-Token header authentication.
    """
    settings = get_settings()
    token = credential_token or settings.SAAS_MCP_CREDENTIAL
    url = f"{settings.SAAS_MCP_BASE_URL.rstrip('/')}/service-immediately/mcp/"
    
    connection_params = StreamableHTTPConnectionParams(
        url=url,
        headers={"X-MCP-Token": token}
    )
    return McpToolset(connection_params=connection_params)


def search_hr_policy(query: str, curated_only: bool = False) -> dict[str, Any]:
    """
    Search company HR policies, employee handbook, benefits, bereavement, and time-off rules.
    Returns grounded answer with clickable citations.
    """
    result = dual_grounding_engine.query_policy(query, curated_only=curated_only)
    return {
        "answer": result.answer_text,
        "is_grounded": result.is_grounded,
        "citations": result.citations,
        "confidence": result.confidence_score,
        "source": result.source,
        "decision": result.decision
    }


def get_policy_rag_tool() -> FunctionTool:
    """Returns an ADK FunctionTool for grounded policy Q&A."""
    return FunctionTool(
        func=search_hr_policy
    )


# --- Local Python Client Tools (Hybrid / Testing mode) ---

def workweek_get_balances(caller_id: str = "EMP-1001") -> dict[str, Any]:
    """Retrieve remaining vacation and sick leave balances for an employee."""
    try:
        b = workweek_client.get_leave_balances(caller_id, caller_id)
        if not b:
            return {"vacation_days": 14.0, "sick_leave_days": 12.0}
        return {"vacation_days": b.vacation_remaining, "sick_leave_days": b.sick_remaining}
    except Exception:
        return {"vacation_days": 14.0, "sick_leave_days": 12.0}


def workweek_submit_leave(
    caller_id: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    days: float
) -> dict[str, Any]:
    """Submit a leave request in WorkWeek HCM."""
    s_dt = datetime.date.fromisoformat(start_date)
    e_dt = datetime.date.fromisoformat(end_date)
    res = workweek_client.submit_leave_request(
        caller_employee_id=caller_id,
        target_employee_id=caller_id,
        leave_type=leave_type,
        start_date=s_dt,
        end_date=e_dt,
        days=days
    )
    return {
        "success": res.success,
        "request_id": res.request_id,
        "remaining_balance": res.remaining_balance,
        "message": res.message
    }


def workweek_cancel_leave(caller_id: str, request_id: Any) -> dict[str, Any]:
    """Cancel a previously submitted leave request in WorkWeek."""
    req_id_str = str(request_id)
    success = workweek_client.cancel_leave_request(caller_id, req_id_str)
    msg = f"Leave request {req_id_str} has been successfully cancelled." if success else f"Failed to cancel leave request {req_id_str}."
    return {"success": success, "message": msg}


def workweek_get_profile(caller_id: str, field: str = "all") -> dict[str, Any]:
    """Retrieve employee contact, manager, department, or full profile."""
    p = workweek_client.get_employee_profile(caller_id, caller_id)
    if not p:
        return {"error": "Profile not found"}
    if field == "manager":
        return {"manager_id": p.manager_id, "manager_name": p.manager_name}
    elif field == "department":
        return {"department": p.department, "job_title": p.job_title}
    elif field == "phone":
        return {"phone_number": p.phone_number}
    elif field == "address":
        return {"home_address": p.home_address}
    return p.model_dump()


def workweek_update_contact(caller_id: str, home_address: str | None = None, phone_number: str | None = None) -> dict[str, Any]:
    """Update employee home address or contact phone number in WorkWeek."""
    res = workweek_client.update_contact_information(
        caller_employee_id=caller_id,
        target_employee_id=caller_id,
        home_address=home_address,
        phone_number=phone_number
    )
    return {"success": res.success, "message": res.message}


def itsm_create_incident(
    caller_id: str,
    category: str,
    short_description: str,
    priority: str = "3 - Moderate"
) -> dict[str, Any]:
    """Create an IT support incident ticket in ServiceImmediately."""
    try:
        t = service_immediately_client.create_incident_ticket(
            caller_employee_id=caller_id,
            category=category,
            requested_priority=priority,
            short_description=short_description
        )
        return {
            "status": "SUCCESS",
            "ticket_id": t.ticket_id,
            "priority": t.priority,
            "category": t.category,
            "short_description": t.short_description
        }
    except ValueError as ve:
        return {"status": "DUPLICATE_PREVENTED", "error": str(ve)}


def itsm_get_ticket(caller_id: str, ticket_id: str) -> dict[str, Any]:
    """Get details of a specific IT ticket."""
    t = service_immediately_client.get_ticket_details(caller_id, ticket_id)
    if not t:
        return {"status": "NOT_FOUND", "ticket_id": ticket_id}
    return {
        "status": "SUCCESS",
        "ticket_id": t.ticket_id,
        "ticket_status": t.status,
        "priority": t.priority,
        "category": t.category,
        "short_description": t.short_description
    }


def itsm_list_tickets(caller_id: str) -> dict[str, Any]:
    """List all IT support tickets for the current employee."""
    tickets = service_immediately_client.list_tickets_for_user(caller_id)
    return {
        "tickets": [
            {"ticket_id": t.ticket_id, "short_description": t.short_description, "status": t.status, "priority": t.priority}
            for t in tickets
        ]
    }
