"""
ADK Specialist Agent Definitions for Enterprise HR & ITSM Operations.
Defines WorkWeek, ServiceImmediately, Policy Q&A, and Saga Coordinator ADK Agents.
"""
from __future__ import annotations

import logging
from typing import Any

from google.adk import Agent
from google.adk.tools import FunctionTool
from src.adk.toolsets import (
    get_itsm_mcp_toolset,
    get_policy_rag_tool,
    get_workweek_mcp_toolset,
    itsm_create_incident,
    itsm_get_ticket,
    itsm_list_tickets,
    workweek_cancel_leave,
    workweek_get_balances,
    workweek_get_profile,
    workweek_submit_leave,
    workweek_update_contact,
)
from src.core.saga import saga_coordinator

logger = logging.getLogger("adk.specialists")


def create_policy_specialist_agent(model: str = "gemini-3.7-flash") -> Agent:
    """Creates the Policy Q&A Specialist ADK Agent (UC-1.1)."""
    return Agent(
        name="policy_specialist",
        model=model,
        description="Specialist agent for answering HR policy, bereavement, benefits, and handbook inquiries.",
        instruction=(
            "You are the Enterprise HR Policy Specialist Agent.\n"
            "Your sole objective is to answer employee questions about company HR policies, PTO, leave entitlements, "
            "bereavement rules, and benefits by retrieving grounded information using the search_hr_policy tool.\n"
            "Always include source policy names and clickable markdown links if available. "
            "Never fabricate or extrapolate unverified policies."
        ),
        tools=[get_policy_rag_tool()]
    )


def create_workweek_specialist_agent(
    model: str = "gemini-3.7-flash",
    use_live_mcp: bool = False
) -> Agent:
    """Creates the WorkWeek HCM Specialist ADK Agent (UC-1.2)."""
    if use_live_mcp:
        tools = [get_workweek_mcp_toolset()]
    else:
        tools = [
            FunctionTool(func=workweek_get_balances),
            FunctionTool(func=workweek_submit_leave),
            FunctionTool(func=workweek_cancel_leave),
            FunctionTool(func=workweek_get_profile),
            FunctionTool(func=workweek_update_contact),
        ]

    return Agent(
        name="workweek_specialist",
        model=model,
        description="Specialist agent for WorkWeek HCM operations: leave balances, time off requests, cancellations, and employee profiles.",
        instruction=(
            "You are the WorkWeek HCM Specialist Agent operating under SDD §3.2.\n"
            "Your role is to assist employees with WorkWeek HR self-service tasks:\n"
            "- Checking remaining vacation and sick leave balances\n"
            "- Submitting vacation, sick, or personal time-off requests\n"
            "- Cancelling previously submitted leave requests\n"
            "- Retrieving profile details (job title, manager, department, phone, address)\n"
            "- Updating personal contact info (home address, phone number)\n"
            "Execute the necessary tool calls and format clear, polite responses."
        ),
        tools=tools
    )


def create_itsm_specialist_agent(
    model: str = "gemini-3.7-flash",
    use_live_mcp: bool = False
) -> Agent:
    """Creates the ServiceImmediately ITSM Specialist ADK Agent (UC-1.3)."""
    if use_live_mcp:
        tools = [get_itsm_mcp_toolset()]
    else:
        tools = [
            FunctionTool(func=itsm_create_incident),
            FunctionTool(func=itsm_get_ticket),
            FunctionTool(func=itsm_list_tickets),
        ]

    return Agent(
        name="itsm_specialist",
        model=model,
        description="Specialist agent for IT incident reporting, hardware requests, and support ticket tracking in ServiceImmediately.",
        instruction=(
            "You are the ServiceImmediately ITSM Specialist Agent operating under SDD §3.2 & §5.1.\n"
            "Your role is to assist employees with IT support operations:\n"
            "- Creating support incident tickets for network, VPN, hardware, software, or access issues\n"
            "- Checking status and details of existing incident tickets (e.g. INC123400)\n"
            "- Listing active support tickets\n"
            "Prevent duplicate tickets within 30 minutes for the same category. Format clear, helpful responses."
        ),
        tools=tools
    )


# --- Saga Distributed Transaction Tools ---

def execute_equipment_procurement_saga(caller_id: str, item_description: str = "Dell UltraSharp 27-inch 4K Monitor") -> dict[str, Any]:
    """Coordinates UC-2.1: Facilities hardware requisition + ServiceImmediately tracking."""
    res = saga_coordinator.execute_equipment_procurement(
        caller_employee_id=caller_id,
        item_description=item_description
    )
    return {
        "success": res.success,
        "message": res.message,
        "escalation_ticket_id": res.escalation_ticket_id
    }


def execute_medical_leave_saga(
    caller_id: str,
    start_date: str,
    end_date: str,
    days: float
) -> dict[str, Any]:
    """Coordinates UC-2.2: WorkWeek Sick_LOA leave + ServiceImmediately email delegation routing."""
    import datetime
    s_dt = datetime.date.fromisoformat(start_date)
    e_dt = datetime.date.fromisoformat(end_date)
    res = saga_coordinator.execute_medical_leave_orchestration(
        caller_employee_id=caller_id,
        start_date=s_dt,
        end_date=e_dt,
        days=days
    )
    return {
        "success": res.success,
        "message": res.message,
        "compensated": res.compensated,
        "escalation_ticket_id": res.escalation_ticket_id
    }


def execute_relocation_saga(caller_id: str, target_location: str = "London Office") -> dict[str, Any]:
    """Coordinates UC-2.3: WorkWeek location update + ServiceImmediately building security access badge."""
    res = saga_coordinator.execute_relocation_and_badge(
        caller_employee_id=caller_id,
        target_location=target_location
    )
    return {
        "success": res.success,
        "message": res.message,
        "escalation_ticket_id": res.escalation_ticket_id
    }


def create_saga_coordinator_agent(model: str = "gemini-3.7-flash") -> Agent:
    """Creates the Cross-System Saga Coordinator ADK Agent (UC-2.1, 2.2, 2.3)."""
    return Agent(
        name="saga_coordinator",
        model=model,
        description="Coordinates complex multi-system workflows: Equipment Procurement, Medical Leave with Delegation, and Relocation Allowance with Badge.",
        instruction=(
            "You are the Enterprise Cross-System Saga Coordinator Agent.\n"
            "You orchestrate multi-step, distributed transactions across WorkWeek HCM and ServiceImmediately ITSM:\n"
            "- UC-2.1: Equipment Procurement (Remote monitor/hardware ordering & facilities ticketing)\n"
            "- UC-2.2: Medical Leave Delegation (Sick leave submission & automated email forwarding configuration)\n"
            "- UC-2.3: Relocation Allowance & Security Badge (Transfer processing & physical building access badge)\n"
            "If any step fails, handle automated backward compensation and report escalation ticket references."
        ),
        tools=[
            FunctionTool(func=execute_equipment_procurement_saga),
            FunctionTool(func=execute_medical_leave_saga),
            FunctionTool(func=execute_relocation_saga),
        ]
    )
