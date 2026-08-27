"""
SaaS MCP Client and Google ADK Tools Package.
"""

from .saas_mcp_client import SaaSMCPClient, saas_mcp_client
from .adk_tools import (
    # WorkWeek Tools
    get_current_employee_id,
    get_employee_balances,
    request_time_off,
    get_personal_info,
    update_personal_info,
    get_leave_requests,
    cancel_leave_request,
    # ServiceImmediately Tools
    list_tickets,
    create_ticket,
    add_ticket_comment,
    update_ticket_status,
    # Registries
    WORKWEEK_ADK_TOOLS,
    ITSM_ADK_TOOLS,
    ALL_SAAS_ADK_TOOLS,
)

__all__ = [
    "SaaSMCPClient",
    "saas_mcp_client",
    "get_current_employee_id",
    "get_employee_balances",
    "request_time_off",
    "get_personal_info",
    "update_personal_info",
    "get_leave_requests",
    "cancel_leave_request",
    "list_tickets",
    "create_ticket",
    "add_ticket_comment",
    "update_ticket_status",
    "WORKWEEK_ADK_TOOLS",
    "ITSM_ADK_TOOLS",
    "ALL_SAAS_ADK_TOOLS",
]
