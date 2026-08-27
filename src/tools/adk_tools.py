"""
Google GenAI / ADK Native Agent Tools for SaaS WorkWeek & ServiceImmediately MCP.

Compatible with Google Agent Development Kit (ADK), Gemini Enterprise Agent Platform,
and Vertex AI Reasoning Engine.
Connects directly to the live FastMCP Streamable HTTP servers using X-MCP-Token.
"""

from typing import Dict, Any, Optional
from src.tools.saas_mcp_client import saas_mcp_client


# ==============================================================================
# WorkWeek HCM MCP Tools (/work-week/mcp/)
# ==============================================================================

async def get_current_employee_id() -> Dict[str, Any]:
    """
    Get the employee ID of the authenticated user session from WorkWeek.

    Returns:
        A dictionary containing the resolved employee ID (e.g., 'EMP-509').
    """
    return await saas_mcp_client.call_tool(
        server_path="work-week/mcp/",
        tool_name="get_current_employee_id",
        arguments={}
    )


async def get_employee_balances(employee_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch current vacation and sick leave balances for a specific WorkWeek employee.

    Args:
        employee_id: The unique employee ID (e.g. 'EMP-509'). Defaults to current session.

    Returns:
        A dictionary containing remaining vacation and sick leave balances.
    """
    target_id = employee_id or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="work-week/mcp/",
        tool_name="get_employee_balances",
        arguments={"employee_id": target_id}
    )


async def request_time_off(
    start_date: str,
    end_date: str,
    leave_type: str = "Vacation",
    days: float = 1.0,
    employee_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit a request for time off into WorkWeek.
    Dates must be in 'YYYY-MM-DD' format. Start date cannot be in the past or after the end date.
    Employee must have sufficient remaining balances.

    Args:
        start_date: The start date formatted in YYYY-MM-DD.
        end_date: The end date formatted in YYYY-MM-DD.
        leave_type: Either 'Vacation' or 'Sick'.
        days: The number of work days requested.
        employee_id: Optional employee ID. Defaults to current session.

    Returns:
        A dictionary confirming the booking and remaining balance.
    """
    target_id = employee_id or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="work-week/mcp/",
        tool_name="request_time_off",
        arguments={
            "employee_id": target_id,
            "start_date": start_date,
            "end_date": end_date,
            "leave_type": leave_type,
            "days": days
        }
    )


async def get_personal_info(employee_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch current personal contact details (home address and phone number) for a WorkWeek employee.

    Args:
        employee_id: Optional employee ID. Defaults to current session.

    Returns:
        A dictionary with address and phone number details.
    """
    target_id = employee_id or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="work-week/mcp/",
        tool_name="get_personal_info",
        arguments={"employee_id": target_id}
    )


async def update_personal_info(
    address: str,
    phone: str,
    employee_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update personal contact details (home address and phone number) for a WorkWeek employee profile.
    Address must be at least 5 characters. Phone number must match regex `^+?[\\d\\s\\-()]{7,20}$`.

    Args:
        address: Residential street address.
        phone: Contact phone number.
        employee_id: Optional employee ID. Defaults to current session.

    Returns:
        A dictionary confirming update status.
    """
    target_id = employee_id or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="work-week/mcp/",
        tool_name="update_personal_info",
        arguments={
            "employee_id": target_id,
            "address": address,
            "phone": phone
        }
    )


async def get_leave_requests(employee_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the history of all requested time off (leave requests) for a WorkWeek employee.

    Args:
        employee_id: Optional employee ID. Defaults to current session.

    Returns:
        A dictionary containing historical leave requests.
    """
    target_id = employee_id or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="work-week/mcp/",
        tool_name="get_leave_requests",
        arguments={"employee_id": target_id}
    )


async def cancel_leave_request(
    request_id: int,
    employee_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Cancel a pending/approved leave request and refund the days back to employee's balance.

    Args:
        request_id: The integer ID of the leave request.
        employee_id: Optional employee ID. Defaults to current session.

    Returns:
        A dictionary confirming cancellation and refunded days.
    """
    target_id = employee_id or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="work-week/mcp/",
        tool_name="cancel_leave_request",
        arguments={
            "employee_id": target_id,
            "request_id": request_id
        }
    )


# ==============================================================================
# ServiceImmediately ITSM MCP Tools (/service-immediately/mcp/)
# ==============================================================================

async def list_tickets(employee_id: Optional[str] = None) -> Dict[str, Any]:
    """
    List all ServiceImmediately incident tickets requested by a specific employee.

    Args:
        employee_id: Optional employee ID. Defaults to current session.

    Returns:
        A list of tickets with ticket_id, short_description, status, and priority.
    """
    target_id = employee_id or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="service-immediately/mcp/",
        tool_name="list_tickets",
        arguments={"employee_id": target_id}
    )


async def create_ticket(
    category: str,
    short_description: str,
    priority: str = "3 - Moderate",
    assignment_group: str = "Service Desk",
    requested_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new ServiceImmediately incident ticket.
    Priority must be one of: '1 - Critical', '2 - High', '3 - Moderate', '4 - Low'.
    Critical priority tickets must describe an active outage, crash, or downtime keyword.

    Args:
        category: Incident category (e.g. 'Hardware', 'HR Services', 'Inquiry / Help').
        short_description: Summary of the issue or request.
        priority: Priority rating.
        assignment_group: Default is 'Service Desk'.
        requested_by: Optional requestor employee ID. Defaults to current session.

    Returns:
        A dictionary containing the created ticket_id.
    """
    target_id = requested_by or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="service-immediately/mcp/",
        tool_name="create_ticket",
        arguments={
            "requested_by": target_id,
            "category": category,
            "short_description": short_description,
            "priority": priority,
            "assignment_group": assignment_group
        }
    )


async def add_ticket_comment(
    ticket_id: str,
    comment: str,
    author: Optional[str] = None
) -> Dict[str, Any]:
    """
    Append a comment/note to the activity log of a ServiceImmediately ticket.

    Args:
        ticket_id: The ticket ID (e.g. 'INC0003359').
        comment: The note or message to append.
        author: Optional author name. Defaults to current session employee ID.

    Returns:
        A dictionary confirming comment addition.
    """
    target_author = author or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="service-immediately/mcp/",
        tool_name="add_ticket_comment",
        arguments={
            "ticket_id": ticket_id,
            "author": target_author,
            "comment": comment
        }
    )


async def update_ticket_status(
    ticket_id: str,
    status: str,
    resolution_notes: str = "",
    updated_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update the life cycle state of a ServiceImmediately ticket ('New', 'In Progress', 'Resolved', 'Closed').
    Valid transitions: New -> In Progress/Closed, In Progress -> Resolved/Closed, Resolved -> In Progress/Closed.

    Args:
        ticket_id: The ticket ID.
        status: The target status.
        resolution_notes: Optional resolution explanation.
        updated_by: Optional updater name. Defaults to current session.

    Returns:
        A dictionary confirming the status update.
    """
    updater = updated_by or await saas_mcp_client.get_current_employee_id()
    return await saas_mcp_client.call_tool(
        server_path="service-immediately/mcp/",
        tool_name="update_ticket_status",
        arguments={
            "ticket_id": ticket_id,
            "status": status,
            "resolution_notes": resolution_notes,
            "updated_by": updater
        }
    )


# ==============================================================================
# Tool Registries
# ==============================================================================

WORKWEEK_ADK_TOOLS = [
    get_current_employee_id,
    get_employee_balances,
    request_time_off,
    get_personal_info,
    update_personal_info,
    get_leave_requests,
    cancel_leave_request
]

ITSM_ADK_TOOLS = [
    list_tickets,
    create_ticket,
    add_ticket_comment,
    update_ticket_status
]

ALL_SAAS_ADK_TOOLS = WORKWEEK_ADK_TOOLS + ITSM_ADK_TOOLS
